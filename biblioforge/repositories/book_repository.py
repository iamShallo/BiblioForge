import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from biblioforge.models.book import (
    Book,
    BookInsights,
    BookStatus,
    ReviewSample,
    TransparencyNote,
)


class BookRepository:
    """Simple JSON-backed repository for demo purposes."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.journal_path = self.storage_path.parent / "books_change_journal.json" if self.storage_path.name == "books.json" else None
        self._cache: List[Book] = self._load()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _book_payload(book: Book) -> Dict[str, Any]:
        return book.to_dict()

    @staticmethod
    def _book_payload_json(book: Book) -> str:
        return json.dumps(BookRepository._book_payload(book), ensure_ascii=False, sort_keys=True)

    def _load_journal(self) -> Dict[str, Any]:
        if not self.journal_path or not self.journal_path.exists():
            return {"next_seq": 1, "entries": []}
        try:
            raw = json.loads(self.journal_path.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                entries = raw.get("entries", [])
                if not isinstance(entries, list):
                    entries = []
                next_seq = raw.get("next_seq", 1)
                try:
                    next_seq = max(1, int(next_seq))
                except Exception:
                    next_seq = 1
                return {"next_seq": next_seq, "entries": [entry for entry in entries if isinstance(entry, dict)]}
        except Exception:
            pass
        return {"next_seq": 1, "entries": []}

    def _save_journal(self, journal: Dict[str, Any]) -> None:
        if not self.journal_path:
            return
        self.journal_path.write_text(json.dumps(journal, indent=2, ensure_ascii=False), encoding="utf-8")

    def _append_journal_entries(self, entries: List[Dict[str, Any]]) -> None:
        if not self.journal_path or not entries:
            return

        journal = self._load_journal()
        next_seq = int(journal.get("next_seq", 1) or 1)
        stored_entries = list(journal.get("entries", []))

        for entry in entries:
            payload = dict(entry)
            payload["seq"] = next_seq
            payload.setdefault("timestamp_epoch", time.time())
            payload.setdefault("timestamp_iso", self._utc_now_iso())
            stored_entries.append(payload)
            next_seq += 1

        self._save_journal({"next_seq": next_seq, "entries": stored_entries})

    def _book_entry(self, operation: str, book: Book, before: Optional[Book] = None, changed_fields: Optional[List[str]] = None) -> Dict[str, Any]:
        after_payload = self._book_payload(book)
        before_payload = self._book_payload(before) if before is not None else None
        return {
            "operation": operation,
            "book_id": book.id,
            "sync_key": self._book_sync_key(book),
            "raw_title": book.raw_title,
            "normalized_title": book.normalized_title,
            "author": book.author,
            "isbn": book.isbn,
            "catalog_ean": book.catalog_ean,
            "status": str(book.status.value if hasattr(book.status, "value") else book.status),
            "changed_fields": changed_fields or [],
            "before_payload_json": json.dumps(before_payload, ensure_ascii=False, sort_keys=True) if before_payload is not None else None,
            "payload_json": json.dumps(after_payload, ensure_ascii=False, sort_keys=True),
        }

    @staticmethod
    def _book_sync_key(book: Book) -> str:
        identifier = str(getattr(book, "isbn", None) or getattr(book, "catalog_ean", None) or "").strip().lower()
        title = str(getattr(book, "normalized_title", None) or getattr(book, "raw_title", None) or "").strip().lower()
        author = str(getattr(book, "author", None) or "").strip().lower()
        return "|".join([identifier, title, author])

    @staticmethod
    def _book_changed_fields(before: Book, after: Book) -> List[str]:
        fields: List[str] = []
        for field_name in Book.__dataclass_fields__:
            if getattr(before, field_name, None) != getattr(after, field_name, None):
                fields.append(field_name)
        return fields

    def _record_book_events(self, events: List[Dict[str, Any]]) -> None:
        self._append_journal_entries(events)

    def _load(self) -> List[Book]:
        if not self.storage_path.exists():
            return []
        
        # Retry logic for file locks during concurrent access
        max_retries = 3
        retry_delay = 0.05  # seconds
        
        for attempt in range(max_retries):
            try:
                # Accept both UTF-8 and UTF-8 with BOM across platforms.
                raw = json.loads(self.storage_path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return []
            except (OSError, IOError):
                # File lock or other I/O error - retry with backoff
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # exponential backoff
                    continue
                return []
            
            if not isinstance(raw, list):
                return []
            return [self._dict_to_book(item) for item in raw if isinstance(item, dict)]
        
        return []

    def _persist(self) -> None:
        payload = [book.to_dict() for book in self._cache]
        
        # Retry logic for file locks during concurrent access
        max_retries = 3
        retry_delay = 0.05  # seconds
        
        for attempt in range(max_retries):
            try:
                self.storage_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                return
            except (OSError, IOError):
                # File lock or other I/O error - retry with backoff
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # exponential backoff
                    continue
                # After all retries, let the error propagate
                raise

    def _refresh_from_disk(self) -> None:
        """Reload cache to reflect external file edits while dashboard is running."""
        self._cache = self._load()

    def list_books(self, status: Optional[BookStatus] = None) -> List[Book]:
        self._refresh_from_disk()
        if status is None:
            return list(self._cache)
        return [b for b in self._cache if b.status == status]

    def get_book(self, book_id: str) -> Optional[Book]:
        self._refresh_from_disk()
        return next((b for b in self._cache if b.id == book_id), None)

    def upsert_book(self, book: Book, *, record_journal: bool = True) -> Book:
        self._refresh_from_disk()
        existing_index = next((idx for idx, current in enumerate(self._cache) if current.id == book.id), None)
        if existing_index is not None:
            existing = self._cache[existing_index]
            if self._book_payload_json(existing) == self._book_payload_json(book):
                return book
            self._cache[existing_index] = book
            self._persist()
            if record_journal:
                self._record_book_events([self._book_entry("update", book, before=existing, changed_fields=self._book_changed_fields(existing, book))])
        else:
            self._cache.append(book)
            self._persist()
            if record_journal:
                self._record_book_events([self._book_entry("add", book)])
        return book

    def upsert_many(self, books: List[Book], *, record_journal: bool = True) -> int:
        """Upsert a batch of books with a single disk write for speed."""
        self._refresh_from_disk()
        cache_map = {b.id: idx for idx, b in enumerate(self._cache)}
        new_count = 0
        journal_entries: List[Dict[str, Any]] = []
        for book in books:
            idx = cache_map.get(book.id)
            if idx is not None:
                existing = self._cache[idx]
                if self._book_payload_json(existing) == self._book_payload_json(book):
                    continue
                self._cache[idx] = book
                journal_entries.append(self._book_entry("update", book, before=existing, changed_fields=self._book_changed_fields(existing, book)))
            else:
                cache_map[book.id] = len(self._cache)
                self._cache.append(book)
                new_count += 1
                journal_entries.append(self._book_entry("add", book))
        # IMPORTANT: Always persist if we received books, even if they were all updates (new_count=0)
        if books:
            self._persist()
            if record_journal:
                self._record_book_events(journal_entries)
        return new_count

    def update_status(self, book_id: str, status: BookStatus, *, record_journal: bool = True) -> Optional[Book]:
        self._refresh_from_disk()
        book = next((current for current in self._cache if current.id == book_id), None)
        if not book:
            return None
        before = self._dict_to_book(book.to_dict())
        book.status = status
        self._persist()
        if record_journal:
            self._record_book_events([self._book_entry("status_update", book, before=before, changed_fields=["status"])])
        return book

    def clear_books(self, status: Optional[BookStatus] = None, *, record_journal: bool = True) -> int:
        """Clear books from storage and return removed count."""
        self._refresh_from_disk()
        if status is None:
            removed_books = list(self._cache)
            removed = len(self._cache)
            self._cache = []
            self._persist()
            if record_journal:
                self._record_book_events([self._book_entry("delete", book, before=book, changed_fields=[]) for book in removed_books])
            return removed

        original_len = len(self._cache)
        removed_books = [book for book in self._cache if book.status == status]
        self._cache = [book for book in self._cache if book.status != status]
        removed = original_len - len(self._cache)
        self._persist()
        if record_journal:
            self._record_book_events([self._book_entry("delete", book, before=book, changed_fields=[]) for book in removed_books])
        return removed

    def delete_book(self, book_id: str, *, record_journal: bool = True) -> bool:
        """Delete a single book by id and return whether it existed."""
        self._refresh_from_disk()
        existing = next((book for book in self._cache if book.id == book_id), None)
        if existing is None:
            return False
        original_len = len(self._cache)
        self._cache = [book for book in self._cache if book.id != book_id]
        removed = len(self._cache) != original_len
        if removed:
            self._persist()
            if record_journal:
                self._record_book_events([self._book_entry("delete", existing, before=existing, changed_fields=[])])
        return removed

    @staticmethod
    def _normalize_status(raw_status: Optional[str]) -> BookStatus:
        if not raw_status:
            return BookStatus.TO_CLEAN

        mapping = {
            "raw": BookStatus.TO_CLEAN,
            "cleaned": BookStatus.IN_PROGRESS,
            "enriched": BookStatus.IN_PROGRESS,
            "pending_review": BookStatus.TO_APPROVE,
            "approved": BookStatus.APPROVED,
            "rejected": BookStatus.TO_CLEAN,
            "da_pulire": BookStatus.TO_CLEAN,
            "in_lavorazione": BookStatus.IN_PROGRESS,
            "da_approvare": BookStatus.TO_APPROVE,
            "approvato": BookStatus.APPROVED,
            "to_clean": BookStatus.TO_CLEAN,
            "in_progress": BookStatus.IN_PROGRESS,
            "to_approve": BookStatus.TO_APPROVE,
        }
        return mapping.get(str(raw_status), BookStatus.TO_CLEAN)

    def seed_sample_if_empty(self) -> None:
        if self._cache:
            return
        sample = Book(
            raw_title="The Name of the Rose - Umberto Eco",
            normalized_title="The Name of the Rose",
            author="Umberto Eco",
            fetched_summary=(
                "In a 14th-century abbey, friar-detective William of Baskerville investigates "
                "murders linked to a forbidden manuscript and a conflict over knowledge."
            ),
            summary_source="seed",
            catalog_ean="9788845292613",
            catalog_publisher="Bompiani",
            catalog_quantity=12,
            catalog_price=18.5,
            isbn="312136632299",
            isbn_10="8804631894",
            published_date="2010-09-14",
            publication_year=2010,
            pages=355,
            cover_url=(
                "https://images-na.ssl-images-amazon.com/images/I/51U0gB02cDL._SX331_BO1,204,203,200_.jpg"
            ),
            publisher="Bompiani",
            categories=["Historical Fiction", "Mystery", "Crime"],
            subtitle="A Medieval Mystery",
            language="it",
            print_type="BOOK",
            info_link="https://books.google.com",
            preview_link="https://books.google.com",
            canonical_volume_link="https://books.google.com",
            goodreads_link="https://www.goodreads.com",
            openlibrary_key="OL82563W",
            first_publish_year=1980,
            edition_count=120,
            average_rating=4.5,
            ratings_count=24000,
            positive_ratio=0.913,
            review_samples=[],
            discarded_information_examples=[],
            insights=BookInsights(
                summary=(
                    "A medieval murder investigation led by William of Baskerville uncovers "
                    "forbidden texts, political schemes, and questions about faith and reason."
                ),
                tags=["Historical Fiction", "Mystery", "Medieval", "Philosophy", "Theology"],
                rejected_information=[
                    TransparencyNote(
                        reason="Movie adaptation details",
                        detail="Left out film references to focus on the book edition.",
                    ),
                    TransparencyNote(
                        reason="Irrelevant plot digression",
                        detail="Removed side anecdotes that do not change the investigation arc.",
                    ),
                ],
            ),
            status=BookStatus.TO_APPROVE,
        )
        self._cache = [sample]
        self._persist()

    @staticmethod
    def _dict_to_book(data: dict) -> Book:
        def _to_float(value: object) -> Optional[float]:
            if value is None:
                return None
            if isinstance(value, bool):
                return float(int(value))
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip().replace(",", ".")
            if not text:
                return None
            try:
                return float(text)
            except (ValueError, TypeError):
                return None

        def _to_int(value: object) -> Optional[int]:
            if value is None:
                return None
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            text = str(value).strip()
            if not text:
                return None
            try:
                return int(float(text))
            except (ValueError, TypeError):
                return None

        def _to_str_list(value: object) -> List[str]:
            if value is None:
                return []
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, str):
                return [item.strip() for item in value.split(",") if item.strip()]
            return []

        if not isinstance(data, dict):
            data = {}

        reviews = []
        for item in data.get("review_samples", []) or []:
            if isinstance(item, dict):
                reviews.append(ReviewSample(**item))

        rejected: List[TransparencyNote] = []
        insights_data = data.get("insights") if isinstance(data.get("insights"), dict) else None
        if insights_data:
            for item in insights_data.get("rejected_information", []) or []:
                if isinstance(item, dict):
                    rejected.append(TransparencyNote(**item))

        insights = None
        if insights_data:
            insights = BookInsights(
                summary=insights_data.get("summary", ""),
                tags=list(insights_data.get("tags", [])),
                rejected_information=rejected,
            )

        normalized_id = str(data.get("id") or "").strip() or str(uuid4())
        return Book(
            raw_title=data.get("raw_title", ""),
            normalized_title=data.get("normalized_title", ""),
            author=data.get("author"),
            fetched_summary=data.get("fetched_summary"),
            summary_source=data.get("summary_source"),
            catalog_ean=data.get("catalog_ean"),
            catalog_publisher=data.get("catalog_publisher"),
            catalog_quantity=_to_int(data.get("catalog_quantity")),
            catalog_price=_to_float(data.get("catalog_price")),
            isbn=data.get("isbn"),
            isbn_10=data.get("isbn_10"),
            published_date=data.get("published_date"),
            publication_year=_to_int(data.get("publication_year")),
            pages=_to_int(data.get("pages")),
            cover_url=data.get("cover_url"),
            publisher=data.get("publisher"),
            categories=_to_str_list(data.get("categories", [])),
            subtitle=data.get("subtitle"),
            language=data.get("language"),
            print_type=data.get("print_type"),
            info_link=data.get("info_link"),
            preview_link=data.get("preview_link"),
            canonical_volume_link=data.get("canonical_volume_link"),
            goodreads_link=data.get("goodreads_link"),
            openlibrary_key=data.get("openlibrary_key"),
            first_publish_year=_to_int(data.get("first_publish_year")),
            edition_count=_to_int(data.get("edition_count")),
            average_rating=_to_float(data.get("average_rating")),
            ratings_count=int(data.get("ratings_count", 0) or 0),
            positive_ratio=_to_float(data.get("positive_ratio")),
            review_samples=reviews,
            discarded_information_examples=_to_str_list(data.get("discarded_information_examples", [])),
            insights=insights,
            reject_attempts=int(data.get("reject_attempts", 0) or 0),
            status=BookRepository._normalize_status(data.get("status")),
            id=normalized_id,
        )
