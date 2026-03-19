import asyncio
import re
from pathlib import Path
from typing import List, Optional, Union
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
        book = asyncio.run(enrich_book(book))
        if not self._is_reliably_enriched(book):
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
        return asyncio.run(
            search_candidates(
                canonical_title,
                normalized_input_author,
                catalog_publisher,
                catalog_ean,
                limit=limit,
            )
        )
    def list_pending(self) -> List[Book]:
        return self.repository.list_books(BookStatus.TO_APPROVE)

    def approve(self, book_id: str) -> Optional[Book]:
        book = self.repository.update_status(book_id, BookStatus.APPROVED)
        if not book:
            return None
        self.approved_repository.upsert_book(book)
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

    def trust_process(self) -> int:
        pending = self.list_pending()
        approved = 0
        for book in pending:
            if self.approve(book.id):
                approved += 1
        return approved

    def remove_from_queue(self, book_id: str) -> bool:
        book = self.repository.get_book(book_id)
        if not book or book.status != BookStatus.TO_APPROVE:
            return False
        return self.repository.delete_book(book_id)

    def ingest_books_from_excel(
        self,
        excel_path: Union[Path, str],
    ) -> int:
        resolved_excel_path = self.resolve_excel_path(excel_path)
        if not resolved_excel_path.exists():
            raise FileNotFoundError(f"Excel file not found: {resolved_excel_path}")

        workbook = pd.read_excel(resolved_excel_path, sheet_name=None)
        queued = 0
        skipped = 0
        seen = set()
        self.last_import_skipped = 0

        title_candidates = ["Title", "Titolo", "Book Title", "Titolo Libro", "Libro", "Nome Libro"]
        author_candidates = ["Author", "Autore", "Authors", "Autori", "Writer"]
        ean_candidates = ["Codice EAN", "EAN", "CodiceEAN", "Barcode", "Codice a barre"]
        publisher_candidates = ["Editore", "Publisher", "Casa Editrice"]
        quantity_candidates = ["Quantita", "Quantità", "Qta", "Stock", "Giacenza"]
        price_candidates = ["Prezzo", "Price", "Prezzo vendita", "Prezzo listino"]

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
            return text

        def _clean_publisher(text: str) -> str:
            text = _fix_mojibake(text)
            text = re.sub(r"^[Vv]\s*-\s*", "", text)
            return text

        def _cell_to_text(value) -> str:
            if value is None or pd.isna(value):
                return ""
            return str(value).strip()

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
            text = _cell_to_text(value)
            if not text:
                return None
            normalized = text.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
            try:
                return float(normalized)
            except ValueError:
                return None

        for _, frame in workbook.items():
            if frame is None or frame.empty:
                continue

            title_col = _pick_column(frame.columns, title_candidates)
            if title_col is None:
                continue
            author_col = _pick_column(frame.columns, author_candidates)
            ean_col = _pick_column(frame.columns, ean_candidates)
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
                raw_title_value = _cell_to_text(row.get(title_col))
                title_value = _clean_title(raw_title_value)
                if not title_value:
                    continue

                title_lower = title_value.lower()
                if any(title_lower.startswith(marker) for marker in noise_markers):
                    continue
                if len(re.sub(r"[^a-z0-9]+", "", title_lower)) < 3:
                    continue

                author_raw = _cell_to_text(row.get(author_col)) if author_col is not None else ""
                author_value = _clean_author(author_raw) if author_raw else ""
                ean_value = _cell_to_text(row.get(ean_col)) if ean_col is not None else ""
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

                # Fast path: enqueue skeleton books without slow enrichment to handle thousands of rows quickly.
                canonical_title = normalize_title(
                    normalized_catalog.get("title") or title_value,
                    normalized_catalog.get("author") or author,
                ) or title_value

                try:
                    # Full enrichment path (slower) to ensure AI/crawling runs like manual ingestion.
                    self.ingest_raw_book(
                        normalized_catalog.get("title") or title_value,
                        normalized_catalog.get("author") or author,
                        catalog_ean=ean_value or None,
                        catalog_publisher=normalized_catalog.get("publisher") or publisher_value or None,
                        catalog_quantity=quantity_value,
                        catalog_price=price_value,
                    )
                    queued += 1
                except BookNotFoundError:
                    skipped += 1
                    continue

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
            else:
                setattr(book, attr, None)

        book.status = BookStatus.IN_PROGRESS
        self.repository.upsert_book(book)

        refreshed = asyncio.run(enrich_book(book))
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

