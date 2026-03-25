import asyncio
import copy
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Union
from uuid import uuid4

import pandas as pd

from biblioforge.models.book import Book, BookStatus
from biblioforge.repositories.book_repository import BookRepository
from biblioforge.services.ai_service import generate_insights, normalize_catalog_entry
from biblioforge.services.crawling_service import enrich_book, search_candidates
from biblioforge.services.normalization_service import normalize_title


class BookNotFoundError(ValueError):
    """Raised when enrichment cannot reliably resolve a book."""


class PipelineController:
    """Coordinates cleaning, enrichment, AI, and persistence."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        processed_dir = Path(__file__).resolve().parent.parent / "data" / "processed"
        cleaned_dir = Path(__file__).resolve().parent.parent / "data" / "cleaned"
        self.project_root = Path(__file__).resolve().parents[2]
        self.package_root = Path(__file__).resolve().parent.parent
        target = storage_path or processed_dir / "books.json"
        approved_target = processed_dir / "approved_books.json"

        self.repository = BookRepository(target)
        self.approved_repository = BookRepository(approved_target)
        self.default_cleaned_excel_path = cleaned_dir / "books_cleaned.xlsx"
        self.last_import_skipped = 0
        self.last_import_skipped_details: List[dict] = []

    @staticmethod
    def _is_reliably_enriched(book: Book) -> bool:
        author = (book.author or "").strip().lower()
        bad_author_markers = ["unknown author", "fonte wikipedia", "wikipedia source"]
        has_real_author = bool(author) and not any(marker in author for marker in bad_author_markers)

        has_trusted_link = any(
            [
                bool(getattr(book, "info_link", None)),
                bool(getattr(book, "canonical_volume_link", None)),
                bool(getattr(book, "openlibrary_key", None)),
            ]
        )

        categories = [str(c).strip().lower() for c in (book.categories or []) if str(c).strip()]
        has_real_categories = any(cat != "unknown genre" for cat in categories)
        has_summary = bool((book.fetched_summary or "").strip())
        has_isbn = bool((book.isbn or "").strip())

        # Require at least one trusted external anchor and meaningful bibliographic evidence.
        return has_trusted_link and (has_real_author or has_real_categories or has_summary or has_isbn)

    @staticmethod
    def _has_minimal_metadata(book: Book) -> bool:
        """True only when enrichment produced externally useful metadata."""
        has_link = any(
            [
                bool(getattr(book, "info_link", None)),
                bool(getattr(book, "canonical_volume_link", None)),
                bool(getattr(book, "openlibrary_key", None)),
                bool(getattr(book, "goodreads_link", None)),
            ]
        )
        has_real_cover = bool(getattr(book, "cover_url", None)) and not PipelineController._looks_like_placeholder_cover(
            getattr(book, "cover_url", None)
        )
        has_real_summary = bool((getattr(book, "fetched_summary", None) or "").strip()) and not PipelineController._has_synthetic_summary(
            book
        )

        # Do not treat synthetic local fallback data as import-ready metadata.
        return has_link or has_real_cover or has_real_summary

    @staticmethod
    def _looks_like_placeholder_cover(url: Optional[str]) -> bool:
        if not url:
            return False
        lowered = str(url).lower()
        if "via.placeholder.com" in lowered:
            return True
        if "covers.openlibrary.org" in lowered and "default=true" in lowered:
            return True
        return False

    @staticmethod
    def _has_synthetic_summary(book: Book) -> bool:
        source = (getattr(book, "summary_source", "") or "").strip().lower()
        summary = (getattr(book, "fetched_summary", None) or "").strip()
        return bool(summary) and source == "local_fallback"

    @staticmethod
    def _apply_candidate_metadata(book: Book, candidate: Optional[dict]) -> Book:
        if not candidate:
            return book

        candidate_link = (candidate.get("info_link") or "").strip() or None
        candidate_cover = (candidate.get("cover_url") or "").strip() or None
        candidate_published_date = (candidate.get("published_date") or "").strip() or None
        candidate_title = (candidate.get("title") or "").strip()
        candidate_authors = (candidate.get("authors") or "").strip()

        if candidate_title:
            canonical = normalize_title(candidate_title, candidate_authors or book.author)
            book.raw_title = canonical or candidate_title
            book.normalized_title = canonical or candidate_title
        if candidate_authors:
            book.author = candidate_authors

        if not getattr(book, "info_link", None) and candidate_link:
            book.info_link = candidate_link
        if (
            (not getattr(book, "cover_url", None) or PipelineController._looks_like_placeholder_cover(getattr(book, "cover_url", None)))
            and candidate_cover
        ):
            book.cover_url = candidate_cover
        if not getattr(book, "openlibrary_key", None) and candidate_link:
            match = re.search(r"openlibrary\.org/works/([^/?#]+)", candidate_link)
            if match:
                book.openlibrary_key = match.group(1)
        if not getattr(book, "published_date", None) and candidate_published_date:
            book.published_date = candidate_published_date
        if (
            not getattr(book, "publication_year", None)
            and candidate_published_date
            and candidate_published_date[:4].isdigit()
        ):
            book.publication_year = int(candidate_published_date[:4])

        # Avoid preserving synthetic fallback summaries when we switched to candidate metadata.
        if PipelineController._has_synthetic_summary(book):
            book.fetched_summary = None
            book.summary_source = None

        return book

    @staticmethod
    def _metadata_score(book: Book) -> int:
        score = 0
        if getattr(book, "info_link", None):
            score += 3
        if getattr(book, "canonical_volume_link", None):
            score += 3
        if getattr(book, "openlibrary_key", None):
            score += 2
        if getattr(book, "goodreads_link", None):
            score += 2
        if getattr(book, "cover_url", None):
            score += 2
        if (getattr(book, "isbn", None) or "").strip():
            score += 2
        if (getattr(book, "isbn_10", None) or "").strip():
            score += 1
        if (getattr(book, "fetched_summary", None) or "").strip():
            score += 2
        if getattr(book, "publisher", None):
            score += 1
        if getattr(book, "pages", None):
            score += 1
        if getattr(book, "publication_year", None):
            score += 1
        if getattr(book, "categories", None):
            score += 1
        return score

    @staticmethod
    def _reset_enrichment_fields(book: Book) -> None:
        for attr in [
            "fetched_summary",
            "summary_source",
            "isbn",
            "isbn_10",
            "published_date",
            "publication_year",
            "pages",
            "cover_url",
            "publisher",
            "categories",
            "subtitle",
            "language",
            "print_type",
            "info_link",
            "preview_link",
            "canonical_volume_link",
            "goodreads_link",
            "openlibrary_key",
            "first_publish_year",
            "edition_count",
            "average_rating",
            "ratings_count",
            "positive_ratio",
            "review_samples",
            "discarded_information_examples",
            "insights",
        ]:
            if attr in {"categories", "review_samples", "discarded_information_examples"}:
                setattr(book, attr, [])
            elif attr == "ratings_count":
                setattr(book, attr, 0)
            else:
                setattr(book, attr, None)

    async def _enrich_with_immediate_retry(self, book: Book) -> Book:
        """Run enrichment and immediately retry once with refreshed catalog hints when metadata is poor."""
        first_pass = await enrich_book(book)
        if self._is_reliably_enriched(first_pass):
            return first_pass

        retry_seed = copy.deepcopy(first_pass)

        refreshed_catalog = normalize_catalog_entry(
            raw_title=first_pass.raw_title,
            raw_author=first_pass.author,
            raw_publisher=getattr(first_pass, "catalog_publisher", None),
        )
        retry_author = refreshed_catalog.get("author") or retry_seed.author
        retry_title_input = refreshed_catalog.get("title") or retry_seed.raw_title
        retry_title = normalize_title(retry_title_input, retry_author)
        if retry_title:
            retry_seed.raw_title = retry_title
            retry_seed.normalized_title = retry_title
        retry_seed.author = retry_author

        self._reset_enrichment_fields(retry_seed)
        second_pass = await enrich_book(retry_seed)

        if self._is_reliably_enriched(second_pass):
            return second_pass

        first_score = self._metadata_score(first_pass)
        second_score = self._metadata_score(second_pass)
        return second_pass if second_score >= first_score else first_pass

    def resolve_excel_path(self, excel_path: Optional[Union[Path, str]] = None) -> Path:
        """Resolve Excel path from absolute or common relative locations."""
        if excel_path is None:
            return self.default_cleaned_excel_path

        provided = Path(excel_path).expanduser()
        if provided.is_absolute():
            return provided

        candidates = [
            Path.cwd() / provided,
            self.project_root / provided,
            self.package_root / provided,
            self.package_root / "data" / "cleaned" / provided.name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        return (self.project_root / provided).resolve()

    def ingest_raw_book(
        self,
        raw_title: str,
        author: Optional[str] = None,
        catalog_ean: Optional[str] = None,
        catalog_publisher: Optional[str] = None,
        catalog_quantity: Optional[int] = None,
        catalog_price: Optional[float] = None,
        allow_low_confidence: bool = False,
    ) -> Book:
        if not (raw_title or "").strip():
            raise BookNotFoundError("Title is empty. Please insert a valid book title.")

        cleaned_author = (author or "").strip() or None
        normalized_catalog = normalize_catalog_entry(
            raw_title=raw_title,
            raw_author=cleaned_author,
            raw_publisher=catalog_publisher,
        )
        normalized_input_title = normalized_catalog.get("title") or raw_title
        normalized_input_author = normalized_catalog.get("author") or cleaned_author
        normalized_title = normalize_title(normalized_input_title, normalized_input_author)
        canonical_title = normalized_title or normalize_title(raw_title, normalized_input_author)
        book = Book(
            raw_title=canonical_title,
            normalized_title=canonical_title,
            author=normalized_input_author,
            catalog_ean=catalog_ean,
            catalog_publisher=normalized_catalog.get("publisher") or catalog_publisher,
            catalog_quantity=catalog_quantity,
            catalog_price=catalog_price,
            status=BookStatus.IN_PROGRESS,
        )
        book = asyncio.run(self._enrich_with_immediate_retry(book))
        if not self._is_reliably_enriched(book):
            if allow_low_confidence:
                # Manual selection can bypass confidence, but not completely empty metadata.
                if self._has_minimal_metadata(book):
                    note = "Manual selection fallback: queued with low confidence, verify metadata before approval."
                    examples = list(getattr(book, "discarded_information_examples", []) or [])
                    if note not in examples:
                        examples.append(note)
                    book.discarded_information_examples = examples
                    book = generate_insights(book)
                    book.status = BookStatus.TO_APPROVE
                    return self.repository.upsert_book(book)

            suggestions = asyncio.run(
                search_candidates(
                    book.normalized_title,
                    book.author,
                    getattr(book, "catalog_publisher", None),
                    getattr(book, "catalog_ean", None),
                )
            )
            suggestion_lines = []
            for idx, item in enumerate(suggestions, start=1):
                title = item.get("title") or "Unknown title"
                authors = item.get("authors") or "Unknown author"
                info_link = item.get("info_link") or ""
                if info_link:
                    suggestion_lines.append(f"{idx}. {title} — {authors} ({info_link})")
                else:
                    suggestion_lines.append(f"{idx}. {title} — {authors}")
            extra = "\n".join(suggestion_lines) if suggestion_lines else ""
            msg = "Book not found with sufficient confidence. Please correct title/author and try again."
            if extra:
                msg = f"{msg}\nPossible matches:\n{extra}"
            raise BookNotFoundError(msg)
        book = generate_insights(book)
        return self.repository.upsert_book(book)

    def ingest_selected_candidate(
        self,
        candidate: dict,
        fallback_title: Optional[str] = None,
        fallback_author: Optional[str] = None,
        catalog_ean: Optional[str] = None,
        catalog_publisher: Optional[str] = None,
        catalog_quantity: Optional[int] = None,
        catalog_price: Optional[float] = None,
    ) -> Book:
        """Ingest a user-selected candidate, preserving candidate metadata when enrichment is weak."""
        selected_title = (candidate.get("title") or fallback_title or "").strip()
        selected_author = (candidate.get("authors") or fallback_author or "").strip() or None
        if not selected_title:
            raise BookNotFoundError("Candidate title is empty. Please select a valid match.")

        try:
            return self.ingest_raw_book(
                selected_title,
                selected_author,
                catalog_ean=catalog_ean,
                catalog_publisher=catalog_publisher,
                catalog_quantity=catalog_quantity,
                catalog_price=catalog_price,
                allow_low_confidence=True,
            )
        except BookNotFoundError:
            normalized_catalog = normalize_catalog_entry(
                raw_title=selected_title,
                raw_author=selected_author,
                raw_publisher=catalog_publisher,
            )
            normalized_input_title = normalized_catalog.get("title") or selected_title
            normalized_input_author = normalized_catalog.get("author") or selected_author
            canonical_title = normalize_title(normalized_input_title, normalized_input_author)

            seed = Book(
                raw_title=canonical_title,
                normalized_title=canonical_title,
                author=normalized_input_author,
                catalog_ean=catalog_ean,
                catalog_publisher=normalized_catalog.get("publisher") or catalog_publisher,
                catalog_quantity=catalog_quantity,
                catalog_price=catalog_price,
                status=BookStatus.IN_PROGRESS,
            )

            seed = self._apply_candidate_metadata(seed, candidate)

            enriched = asyncio.run(self._enrich_with_immediate_retry(seed))
            enriched = self._apply_candidate_metadata(enriched, candidate)

            if not self._has_minimal_metadata(enriched):
                raise BookNotFoundError(
                    "Selected match could not provide enough metadata. Try another candidate or add ISBN/EAN."
                )

            note = "Manual selected-candidate fallback: queued with preserved external metadata."
            examples = list(getattr(enriched, "discarded_information_examples", []) or [])
            if note not in examples:
                examples.append(note)
            enriched.discarded_information_examples = examples
            enriched = generate_insights(enriched)
            enriched.status = BookStatus.TO_APPROVE
            return self.repository.upsert_book(enriched)

    def find_candidates(
        self,
        raw_title: str,
        author: Optional[str] = None,
        catalog_publisher: Optional[str] = None,
        catalog_ean: Optional[str] = None,
        limit: int = 6,
    ) -> List[dict]:
        """Return candidate matches for a raw query (title/author/publisher/ean)."""
        cleaned_author = (author or "").strip() or None
        normalized_catalog = normalize_catalog_entry(
            raw_title=raw_title,
            raw_author=cleaned_author,
            raw_publisher=catalog_publisher,
        )
        normalized_input_title = normalized_catalog.get("title") or raw_title
        normalized_input_author = normalized_catalog.get("author") or cleaned_author
        canonical_title = normalize_title(normalized_input_title, normalized_input_author)
        strict_results = asyncio.run(
            search_candidates(
                canonical_title,
                normalized_input_author,
                catalog_publisher,
                catalog_ean,
                limit=limit,
            )
        )
        if strict_results:
            return strict_results

        # Fallback 1: same title but no author constraint.
        relaxed_results = asyncio.run(
            search_candidates(
                canonical_title,
                None,
                catalog_publisher,
                catalog_ean,
                limit=limit,
            )
        )
        if relaxed_results:
            return relaxed_results

        # Fallback 2: raw title text without catalog normalization.
        raw_title_for_search = normalize_title(raw_title, cleaned_author) or (raw_title or "").strip()
        if raw_title_for_search and raw_title_for_search != canonical_title:
            raw_results = asyncio.run(
                search_candidates(
                    raw_title_for_search,
                    cleaned_author,
                    catalog_publisher,
                    catalog_ean,
                    limit=limit,
                )
            )
            if raw_results:
                return raw_results

        # Fallback 3: direct lookup by EAN/ISBN when present.
        code_value = (catalog_ean or "").strip()
        if code_value:
            code_results = asyncio.run(
                search_candidates(
                    code_value,
                    None,
                    None,
                    code_value,
                    limit=limit,
                )
            )
            if code_results:
                return code_results

        return []

    def retry_skipped_entries(
        self,
        skipped_entries: List[dict],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> tuple[int, List[dict]]:
        """Retry skipped rows with bounded concurrency and batch persistence."""
        if not skipped_entries:
            return 0, []

        async def _retry_entries(items: List[dict]) -> tuple[int, List[dict]]:
            total = len(items)
            processed = 0
            resolved = 0
            unresolved: List[dict] = []
            max_concurrency = max(1, int(os.getenv("BIBLIOFORGE_RETRY_CONCURRENCY", "16")))
            batch_size = max(max_concurrency, int(os.getenv("BIBLIOFORGE_RETRY_BATCH", "160")))
            semaphore = asyncio.Semaphore(max_concurrency)
            cache = {}

            async def _retry_one(entry: dict, entry_index: int) -> tuple[Optional[Book], Optional[dict]]:
                entry_title = (entry.get("title") or "").strip()
                entry_author = (entry.get("author") or "").strip() or None
                entry_ean = str(entry.get("ean") or "").strip() or None
                entry_publisher = (entry.get("publisher") or "").strip() or None
                query_title = entry_title or (entry_ean or "")

                if not query_title:
                    return None, {
                        "index": entry_index,
                        "title": entry.get("title"),
                        "author": entry.get("author"),
                        "ean": entry_ean,
                        "publisher": entry.get("publisher"),
                        "reason": "Missing title/EAN for retry",
                    }

                cache_key = (query_title.casefold(), (entry_author or "").casefold())
                cached_template = cache.get(cache_key)
                if cached_template is not None:
                    cached = copy.deepcopy(cached_template)
                    cached.id = str(uuid4())
                    cached.catalog_ean = entry_ean
                    cached.catalog_publisher = entry_publisher
                    cached.status = BookStatus.TO_APPROVE
                    return cached, None

                async with semaphore:
                    try:
                        normalized_catalog = normalize_catalog_entry(
                            raw_title=query_title,
                            raw_author=entry_author,
                            raw_publisher=entry_publisher,
                        )
                        normalized_input_title = normalized_catalog.get("title") or query_title
                        normalized_input_author = normalized_catalog.get("author") or entry_author
                        canonical_title = normalize_title(normalized_input_title, normalized_input_author)

                        seed = Book(
                            raw_title=canonical_title or normalized_input_title,
                            normalized_title=canonical_title or normalized_input_title,
                            author=normalized_input_author,
                            catalog_ean=entry_ean,
                            catalog_publisher=normalized_catalog.get("publisher") or entry_publisher,
                            status=BookStatus.IN_PROGRESS,
                        )

                        candidate_results = await search_candidates(
                            normalized_title=query_title,
                            author=entry_author,
                            publisher=entry_publisher,
                            catalog_ean=entry_ean,
                            limit=1,
                        )
                        top_candidate = candidate_results[0] if candidate_results else None
                        if top_candidate:
                            seed = self._apply_candidate_metadata(seed, top_candidate)

                        book = await self._enrich_with_immediate_retry(seed)
                        if top_candidate:
                            book = self._apply_candidate_metadata(book, top_candidate)

                        if not self._is_reliably_enriched(book):
                            if not self._has_minimal_metadata(book):
                                return None, {
                                    "index": entry_index,
                                    "title": entry.get("title"),
                                    "author": entry.get("author"),
                                    "ean": entry_ean,
                                    "publisher": entry.get("publisher"),
                                    "reason": "No reliable metadata found from Google Books/Goodreads",
                                }

                            note = "Low-confidence retry fallback: verify title/author/isbn before approval."
                            examples = list(getattr(book, "discarded_information_examples", []) or [])
                            if note not in examples:
                                examples.append(note)
                            book.discarded_information_examples = examples

                        book = await asyncio.to_thread(generate_insights, book)
                        book.status = BookStatus.TO_APPROVE
                        cache[cache_key] = copy.deepcopy(book)
                        return book, None
                    except Exception as exc:
                        return None, {
                            "index": entry_index,
                            "title": entry.get("title"),
                            "author": entry.get("author"),
                            "ean": entry_ean,
                            "publisher": entry.get("publisher"),
                            "reason": f"Retry failed: {exc}",
                        }

            item_offset = 0
            for idx in range(0, len(items), batch_size):
                chunk = items[idx : idx + batch_size]
                tasks = [_retry_one(entry, item_offset + i) for i, entry in enumerate(chunk)]
                results = await asyncio.gather(*tasks)
                item_offset += len(chunk)

                to_insert = [book for book, error in results if book is not None and error is None]
                errors = [error for _, error in results if error is not None]

                if to_insert:
                    self.repository.upsert_many(to_insert)
                resolved += len(to_insert)
                unresolved.extend(errors)

                processed += len(chunk)
                if progress_callback:
                    try:
                        progress_callback(processed, total)
                    except Exception:
                        pass

            return resolved, unresolved

        return asyncio.run(_retry_entries(skipped_entries))
    
    def _save_skipped_report(self, skipped_entries: List[dict]) -> str:
        """Save skipped entries to a JSON report file."""
        reports_dir = self.project_root / "artifacts" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"import_skipped_{timestamp}.json"
        
        # Ensure EAN values are strings to prevent float conversion
        cleaned_entries = []
        for entry in skipped_entries:
            cleaned_entry = entry.copy()
            if cleaned_entry.get("ean"):
                cleaned_entry["ean"] = str(cleaned_entry["ean"]).split('.')[0]  # Remove .0 if present
            cleaned_entries.append(cleaned_entry)
        
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "total_skipped": len(cleaned_entries),
            "skipped_entries": cleaned_entries
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        self.last_import_skipped_report_path = str(report_path)
        return str(report_path)
    
    def get_last_skipped_report_path(self) -> Optional[str]:
        """Get the path to the last generated skipped report."""
        return getattr(self, "last_import_skipped_report_path", None)
    
    def list_pending(self) -> List[Book]:
        return self.repository.list_books(BookStatus.TO_APPROVE)

    def approve(self, book_id: str) -> Optional[Book]:
        # Move a book from the review queue to the final DB and remove it from the queue file.
        book = self.repository.get_book(book_id)
        if not book:
            return None

        book.status = BookStatus.APPROVED
        self.approved_repository.upsert_book(book)
        self.repository.delete_book(book_id)
        return book

    def approve_with_edits(self, book_id: str, summary: str, tags: List[str]) -> Optional[Book]:
        book = self.repository.get_book(book_id)
        if not book:
            return None

        if book.insights:
            book.insights.summary = summary
            book.insights.tags = tags
            self.repository.upsert_book(book)
        return self.approve(book_id)

    def clear_approved(self) -> int:
        return self.approved_repository.clear_books()

    def restore_from_approved(self, book_id: str) -> bool:
        """Move a book from final DB back into the review queue."""
        book = self.approved_repository.get_book(book_id)
        if not book:
            return False

        book.status = BookStatus.TO_APPROVE
        self.repository.upsert_book(book)
        self.approved_repository.delete_book(book_id)
        return True

    def trust_process(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> int:
        pending = self.list_pending()
        total = len(pending)
        approved = 0
        for idx, book in enumerate(pending):
            if self.approve(book.id):
                approved += 1
            if progress_callback:
                progress_callback(idx + 1, total)
        return approved

    def remove_from_queue(self, book_id: str) -> bool:
        book = self.repository.get_book(book_id)
        if not book or book.status != BookStatus.TO_APPROVE:
            return False
        return self.repository.delete_book(book_id)

    def ingest_books_from_excel(
        self,
        excel_path: Union[Path, str],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        resolved_excel_path = self.resolve_excel_path(excel_path)
        if not resolved_excel_path.exists():
            raise FileNotFoundError(f"Excel file not found: {resolved_excel_path}")

        workbook = pd.read_excel(resolved_excel_path, sheet_name=None)
        queued = 0
        skipped = 0
        seen = set()
        self.last_import_skipped = 0
        self.last_import_skipped_details = []
        self.last_import_skipped_report_path = None

        title_candidates = ["Title", "Titolo", "Book Title", "Titolo Libro", "Libro", "Nome Libro"]
        isbn_candidates = ["ISBN", "ISBN-13", "ISBN13", "Codice ISBN", "EAN/ISBN", "Codice libro"]
        author_candidates = ["Author", "Autore", "Authors", "Autori", "Writer"]
        ean_candidates = ["Codice EAN", "EAN", "CodiceEAN", "Barcode", "Codice a barre"]
        publisher_candidates = ["Editore", "Publisher", "Casa Editrice"]
        quantity_candidates = ["Quantita", "Quantità", "Qta", "Stock", "Giacenza"]
        price_candidates = [
            "Prezzo",
            "Price",
            "Prezzo vendita",
            "Prezzo listino",
            "PVP",
            "Prezzo copertina",
            "Importo",
            "Costo",
        ]

        def _env_truthy(name: str, default: bool = True) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return default
            return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

        allow_catalog_only_fallback = _env_truthy("BIBLIOFORGE_IMPORT_ALLOW_CATALOG_FALLBACK", True)

        def _pick_column(columns, candidates):
            exact = {str(c): c for c in columns}
            for candidate in candidates:
                if candidate in exact:
                    return exact[candidate]

            lower = {str(c).strip().lower(): c for c in columns}
            for candidate in candidates:
                if candidate.strip().lower() in lower:
                    return lower[candidate.strip().lower()]

            # Fuzzy fallback: match by containment for messy headers.
            lowered_columns = {str(c).strip().lower(): c for c in columns}
            for col_lower, original in lowered_columns.items():
                for candidate in candidates:
                    cand = candidate.strip().lower()
                    if cand and (cand in col_lower or col_lower in cand):
                        return original
            return None

        def _fix_mojibake(text: str) -> str:
            """Fix common mojibake (UTF-8 mis-decoded as Latin-1) and stray chars."""
            if not text:
                return ""

            # Try to reverse common mojibake (Ã, ã) by re-decoding.
            decoded = text
            try:
                decoded = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            except Exception:
                decoded = text

            replacements = {
                "Â«": "«",
                "Â»": "»",
                "Â": "",
                "â€™": "'",
                "â€œ": "\"",
                "â€": "\"",
                "â€“": "-",
                "ã€€": " ",
                "ãœ": "Ü",
                "ã¼": "ü",
                "ã¶": "ö",
                "ã¤": "ä",
                "ã‰": "É",
                "ã©": "é",
                "ã¨": "è",
                "ã²": "ò",
                "ã¹": "ù",
            }
            for bad, good in replacements.items():
                decoded = decoded.replace(bad, good)

            decoded = re.sub(r"\s+", " ", decoded)
            return decoded.strip(" \"'“”‘’””")

        def _clean_title(text: str) -> str:
            text = _fix_mojibake(text)
            text = re.sub(r"^[\W_]+", "", text)
            return text.strip()

        def _clean_author(text: str) -> str:
            text = _fix_mojibake(text)
            # Strip common curator/editor markers that hurt search precision.
            text = re.sub(r"\([^)]*\)", " ", text)
            text = re.sub(r"\b(CUR\.?|A\s+CURA\s+DI|ED\.?|TRAD\.?|TRADOTTO\s+DA)\b", " ", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*;\s*", ";", text)
            chunks = [part.strip() for part in text.split(";") if part.strip()]
            primary = chunks[0] if chunks else text
            primary = re.sub(r"\s+", " ", primary).strip(" ,;:-")
            return primary

        def _clean_publisher(text: str) -> str:
            text = _fix_mojibake(text)
            text = re.sub(r"^[Vv]\s*-\s*", "", text)
            return text

        def _looks_like_catalog_book(entry: dict) -> bool:
            title = str(entry.get("title") or "").strip()
            author = str(entry.get("author") or "").strip()
            ean = str(entry.get("ean") or "").strip().upper()
            publisher = str(entry.get("publisher") or "").strip()

            if not title:
                return False
            if len(title) < 3:
                return False
            if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", title):
                return False

            alpha_count = len(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]", title))
            if alpha_count < 3:
                return False

            has_code = bool(re.fullmatch(r"[0-9X]{8,14}", ean))
            has_author = bool(author and re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", author))
            has_publisher = bool(publisher and len(publisher) >= 3)
            return has_code or has_author or has_publisher

        def _cell_to_text(value) -> str:
            if value is None or pd.isna(value):
                return ""
            return str(value).strip()

        def _clean_catalog_code(value) -> str:
            text = _cell_to_text(value)
            if not text:
                return ""
            # Normalize Excel numeric-like values and keep only ISBN/EAN-safe chars.
            text = text.split(".")[0] if text.endswith(".0") else text
            compact = re.sub(r"[^0-9Xx]", "", text)
            return compact.upper()

        def _to_int(value) -> Optional[int]:
            text = _cell_to_text(value)
            if not text:
                return None
            text = text.replace(".", "").replace(",", ".")
            try:
                return int(float(text))
            except ValueError:
                return None

        def _to_float(value) -> Optional[float]:
            if isinstance(value, (int, float)) and not pd.isna(value):
                return float(value)

            text = _cell_to_text(value)
            if not text:
                return None

            normalized = text.replace("€", "").replace("EUR", "").replace("eur", "")
            normalized = re.sub(r"[^0-9,.-]", "", normalized)
            if not normalized:
                return None

            # Heuristic parsing for both EU (1.234,56) and US (1,234.56) formats.
            if "," in normalized and "." in normalized:
                last_comma = normalized.rfind(",")
                last_dot = normalized.rfind(".")
                if last_comma > last_dot:
                    normalized = normalized.replace(".", "").replace(",", ".")
                else:
                    normalized = normalized.replace(",", "")
            elif "," in normalized:
                normalized = normalized.replace(".", "").replace(",", ".")

            try:
                return float(normalized)
            except ValueError:
                return None

        entries: List[dict] = []

        for _, frame in workbook.items():
            if frame is None or frame.empty:
                continue

            title_col = _pick_column(frame.columns, title_candidates)
            isbn_col = _pick_column(frame.columns, isbn_candidates)
            ean_col = _pick_column(frame.columns, ean_candidates)
            if title_col is None and isbn_col is None and ean_col is None:
                continue
            author_col = _pick_column(frame.columns, author_candidates)
            publisher_col = _pick_column(frame.columns, publisher_candidates)
            quantity_col = _pick_column(frame.columns, quantity_candidates)
            price_col = _pick_column(frame.columns, price_candidates)

            noise_markers = (
                "totale",
                "attenzione",
                "pvp",
                "n.b",
                "nb:",
                "note",
                "avviso",
            )

            for _, row in frame.iterrows():
                raw_title_value = _cell_to_text(row.get(title_col)) if title_col is not None else ""
                title_value = _clean_title(raw_title_value)
                isbn_value = _clean_catalog_code(row.get(isbn_col)) if isbn_col is not None else ""
                ean_value = _clean_catalog_code(row.get(ean_col)) if ean_col is not None else ""
                catalog_code = isbn_value or ean_value

                if not title_value and not catalog_code:
                    continue

                if not title_value and catalog_code:
                    title_value = catalog_code

                title_lower = title_value.lower()
                if any(title_lower.startswith(marker) for marker in noise_markers):
                    continue
                if len(re.sub(r"[^a-z0-9]+", "", title_lower)) < 3:
                    continue

                author_raw = _cell_to_text(row.get(author_col)) if author_col is not None else ""
                author_value = _clean_author(author_raw) if author_raw else ""
                publisher_raw = _cell_to_text(row.get(publisher_col)) if publisher_col is not None else ""
                publisher_value = _clean_publisher(publisher_raw) if publisher_raw else ""
                quantity_value = _to_int(row.get(quantity_col)) if quantity_col is not None else None
                price_value = _to_float(row.get(price_col)) if price_col is not None else None
                dedupe_key = (title_value.casefold(), author_value.casefold())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                author = author_value or None
                normalized_catalog = normalize_catalog_entry(
                    raw_title=title_value,
                    raw_author=author,
                    raw_publisher=publisher_value or None,
                )

                entries.append(
                    {
                        "title": normalized_catalog.get("title") or title_value,
                        "author": normalized_catalog.get("author") or author,
                        "publisher": normalized_catalog.get("publisher") or publisher_value or None,
                        "ean": catalog_code or None,
                        "quantity": quantity_value,
                        "price": price_value,
                    }
                )

        if not entries:
            self.last_import_skipped = skipped
            if progress_callback:
                progress_callback(0, 0)
            return queued

        async def _process_entries(items: List[dict]) -> None:
            nonlocal queued, skipped
            processed = 0
            total = len(items)
            max_concurrency = max(1, int(os.getenv("BIBLIOFORGE_IMPORT_CONCURRENCY", "20")))
            batch_size = max(20, int(os.getenv("BIBLIOFORGE_IMPORT_BATCH", "200")))
            semaphore = asyncio.Semaphore(max_concurrency)
            cache = {}
            skipped_entries = []

            async def _enrich_one(entry: dict, entry_index: int) -> Optional[Book]:
                key = (entry.get("title", "").casefold(), (entry.get("author") or "").casefold())

                # Serve from cache when the same title/author repeats.
                if key in cache:
                    cached = copy.deepcopy(cache[key])
                    cached.id = str(uuid4())
                    cached.catalog_ean = entry.get("ean")
                    cached.catalog_publisher = entry.get("publisher")
                    cached.catalog_quantity = entry.get("quantity")
                    cached.catalog_price = entry.get("price")
                    cached.status = BookStatus.TO_APPROVE
                    return cached

                async with semaphore:
                    try:
                        book = Book(
                            raw_title=entry.get("title"),
                            normalized_title=normalize_title(entry.get("title"), entry.get("author")),
                            author=entry.get("author"),
                            catalog_ean=entry.get("ean"),
                            catalog_publisher=entry.get("publisher"),
                            catalog_quantity=entry.get("quantity"),
                            catalog_price=entry.get("price"),
                            status=BookStatus.IN_PROGRESS,
                        )
                        book = await self._enrich_with_immediate_retry(book)
                        if not self._is_reliably_enriched(book):
                            # Try fallback: search by EAN if available
                            ean_value = (entry.get("ean") or "").strip()
                            if ean_value and len(ean_value) >= 8:
                                try:
                                    # Search using EAN as primary identifier
                                    ean_candidates = await search_candidates(
                                        normalized_title=ean_value,
                                        author=None,
                                        publisher=None,
                                        catalog_ean=ean_value,
                                        limit=1
                                    )
                                    if ean_candidates and len(ean_candidates) > 0:
                                        # Found via EAN, try to enrich again with EAN search result
                                        top_result = ean_candidates[0]
                                        book.raw_title = top_result.get("title", book.raw_title)
                                        book.normalized_title = top_result.get("title", book.normalized_title)
                                        book.author = top_result.get("authors", book.author)
                                        book = await enrich_book(book)
                                        if self._is_reliably_enriched(book):
                                            book = generate_insights(book)
                                            book.status = BookStatus.TO_APPROVE
                                            cache[key] = book
                                            return book
                                except Exception:
                                    pass

                            # Try fallback: resolve best candidate by title/author and enrich again.
                            try:
                                candidate_results = await search_candidates(
                                    normalized_title=entry.get("title") or "",
                                    author=entry.get("author") or "",
                                    publisher=entry.get("publisher") or None,
                                    catalog_ean=entry.get("ean") or None,
                                    limit=1,
                                )
                                if candidate_results:
                                    top_result = candidate_results[0]
                                    candidate_title = (top_result.get("title") or "").strip()
                                    candidate_authors = (top_result.get("authors") or "").strip()
                                    if candidate_title:
                                        canonical_candidate_title = normalize_title(
                                            candidate_title,
                                            candidate_authors or book.author,
                                        )
                                        book.raw_title = canonical_candidate_title or candidate_title
                                        book.normalized_title = canonical_candidate_title or candidate_title
                                    if candidate_authors:
                                        book.author = candidate_authors

                                    book = await enrich_book(book)
                                    if self._is_reliably_enriched(book):
                                        book = generate_insights(book)
                                        book.status = BookStatus.TO_APPROVE
                                        cache[key] = book
                                        return book
                            except Exception:
                                pass

                            # Queue unresolved items only when we still have meaningful metadata.
                            has_minimal_metadata = self._has_minimal_metadata(book)

                            if has_minimal_metadata:
                                note = "Low-confidence import fallback: verify title/author/isbn before approval."
                                examples = list(getattr(book, "discarded_information_examples", []) or [])
                                if note not in examples:
                                    examples.append(note)
                                book.discarded_information_examples = examples
                                book = generate_insights(book)
                                book.status = BookStatus.TO_APPROVE
                                cache[key] = book
                                return book

                            if allow_catalog_only_fallback and _looks_like_catalog_book(entry):
                                # Keep plausible catalog rows in the review queue even without trusted external metadata.
                                entry_title = entry.get("title") or book.raw_title
                                entry_author = entry.get("author") or book.author
                                canonical_entry_title = normalize_title(entry_title, entry_author) or entry_title
                                book.raw_title = canonical_entry_title
                                book.normalized_title = canonical_entry_title
                                book.author = entry_author
                                book.catalog_ean = entry.get("ean")
                                book.catalog_publisher = entry.get("publisher")
                                book.catalog_quantity = entry.get("quantity")
                                book.catalog_price = entry.get("price")

                                note = (
                                    "Catalog-only fallback: queued without trusted external metadata. "
                                    "Verify title/author/isbn before approval."
                                )
                                examples = list(getattr(book, "discarded_information_examples", []) or [])
                                if note not in examples:
                                    examples.append(note)
                                book.discarded_information_examples = examples
                                book = generate_insights(book)
                                book.status = BookStatus.TO_APPROVE
                                cache[key] = book
                                return book

                            skipped_entries.append(
                                {
                                    "index": entry_index,
                                    "title": entry.get("title"),
                                    "author": entry.get("author"),
                                    "ean": str(entry.get("ean")) if entry.get("ean") else None,
                                    "publisher": entry.get("publisher"),
                                    "reason": "No reliable metadata found and catalog row looked invalid/noisy",
                                }
                            )
                            return None
                        book = generate_insights(book)
                        book.status = BookStatus.TO_APPROVE
                        cache[key] = book
                        return book
                    except Exception as e:
                        skipped_entries.append({
                            "index": entry_index,
                            "title": entry.get("title"),
                            "author": entry.get("author"),
                            "ean": entry.get("ean"),
                            "publisher": entry.get("publisher"),
                            "reason": f"Exception during enrichment: {str(e)}"
                        })
                        return None

            chunk_offset = 0
            for idx in range(0, len(items), batch_size):
                chunk = items[idx : idx + batch_size]
                tasks = [_enrich_one(entry, chunk_offset + i) for i, entry in enumerate(chunk)]
                results = await asyncio.gather(*tasks)
                to_insert = [b for b in results if b]
                queued += len(to_insert)
                skipped += len(chunk) - len(to_insert)
                chunk_offset += len(chunk)
                processed += len(chunk)
                if to_insert:
                    self.repository.upsert_many(to_insert)

                if progress_callback:
                    try:
                        progress_callback(processed, total)
                    except Exception:
                        pass
            
            # Save skipped entries to a JSON report
            if skipped_entries:
                self.last_import_skipped_details = skipped_entries
                self._save_skipped_report(skipped_entries)

        asyncio.run(_process_entries(entries))

        self.last_import_skipped = skipped
        return queued


    def reject_and_retry(self, book_id: str) -> Optional[Book]:
        book = self.repository.get_book(book_id)
        if not book:
            return None

        if not (book.author or "").strip():
            refreshed_catalog = normalize_catalog_entry(
                raw_title=book.raw_title,
                raw_author=book.author,
                raw_publisher=getattr(book, "catalog_publisher", None),
            )
            book.author = refreshed_catalog.get("author") or book.author
            inferred_title = refreshed_catalog.get("title") or book.raw_title
            if inferred_title:
                canonical_title = normalize_title(inferred_title, book.author)
                book.raw_title = canonical_title
                book.normalized_title = canonical_title

        previous_summary = book.insights.summary if book.insights else None
        regeneration_token = str(uuid4())
        book.reject_attempts = int(book.reject_attempts or 0) + 1

        # Reset enrichment-derived fields so stale metadata/summary are not reused.
        self._reset_enrichment_fields(book)

        book.status = BookStatus.IN_PROGRESS
        self.repository.upsert_book(book)

        refreshed = asyncio.run(self._enrich_with_immediate_retry(book))
        refreshed = generate_insights(
            refreshed,
            regeneration_token=regeneration_token,
            previous_summary=previous_summary,
        )
        return self.repository.upsert_book(refreshed)

    def get(self, book_id: str) -> Optional[Book]:
        return self.repository.get_book(book_id)

    def list_approved(self) -> List[Book]:
        return self.approved_repository.list_books(BookStatus.APPROVED)

    def ensure_review_metadata(self, book_id: str) -> Optional[Book]:
        """Ensure pending-review book has metadata on first opening, without manual reject."""
        book = self.repository.get_book(book_id)
        if not book:
            return None

        has_summary = bool((getattr(book, "fetched_summary", None) or "").strip())
        has_cover = bool(getattr(book, "cover_url", None))
        has_link = bool(
            getattr(book, "info_link", None)
            or getattr(book, "canonical_volume_link", None)
            or getattr(book, "goodreads_link", None)
            or getattr(book, "openlibrary_key", None)
        )
        synthetic_summary = self._has_synthetic_summary(book)
        placeholder_cover = self._looks_like_placeholder_cover(getattr(book, "cover_url", None))

        if self._has_minimal_metadata(book) and (has_summary or has_cover or has_link) and not (
            synthetic_summary or placeholder_cover
        ):
            return book

        refreshed_catalog = normalize_catalog_entry(
            raw_title=book.raw_title,
            raw_author=book.author,
            raw_publisher=getattr(book, "catalog_publisher", None),
        )
        book.author = refreshed_catalog.get("author") or book.author
        inferred_title = refreshed_catalog.get("title") or book.raw_title
        if inferred_title:
            canonical_title = normalize_title(inferred_title, book.author)
            if canonical_title:
                book.raw_title = canonical_title
                book.normalized_title = canonical_title

        previous_summary = book.insights.summary if book.insights else None
        regeneration_token = str(uuid4())
        # Drop stale fallback metadata before automatic refresh.
        self._reset_enrichment_fields(book)
        book.status = BookStatus.IN_PROGRESS
        self.repository.upsert_book(book)

        refreshed = asyncio.run(self._enrich_with_immediate_retry(book))

        # If still weak, try resolving a top candidate and merge its metadata.
        if not self._has_minimal_metadata(refreshed) or self._has_synthetic_summary(refreshed):
            candidates = asyncio.run(
                search_candidates(
                    refreshed.normalized_title or refreshed.raw_title,
                    refreshed.author,
                    getattr(refreshed, "catalog_publisher", None),
                    getattr(refreshed, "catalog_ean", None),
                    limit=1,
                )
            )
            if candidates:
                refreshed = self._apply_candidate_metadata(refreshed, candidates[0])

        refreshed = generate_insights(
            refreshed,
            regeneration_token=regeneration_token,
            previous_summary=previous_summary,
        )
        refreshed.status = BookStatus.TO_APPROVE
        return self.repository.upsert_book(refreshed)

