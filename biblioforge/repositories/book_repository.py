import json
import time
from pathlib import Path
from typing import List, Optional
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
        self._cache: List[Book] = self._load()

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

    def upsert_book(self, book: Book) -> Book:
        existing = self.get_book(book.id)
        if existing:
            self._cache = [book if b.id == book.id else b for b in self._cache]
        else:
            self._cache.append(book)
        self._persist()
        return book

    def upsert_many(self, books: List[Book]) -> int:
        """Upsert a batch of books with a single disk write for speed."""
        self._refresh_from_disk()
        cache_map = {b.id: idx for idx, b in enumerate(self._cache)}
        new_count = 0
        for book in books:
            idx = cache_map.get(book.id)
            if idx is not None:
                self._cache[idx] = book
            else:
                cache_map[book.id] = len(self._cache)
                self._cache.append(book)
                new_count += 1
        # IMPORTANT: Always persist if we received books, even if they were all updates (new_count=0)
        if books:
            self._persist()
        return new_count

    def update_status(self, book_id: str, status: BookStatus) -> Optional[Book]:
        self._refresh_from_disk()
        book = self.get_book(book_id)
        if not book:
            return None
        book.status = status
        self._persist()
        return book

    def clear_books(self, status: Optional[BookStatus] = None) -> int:
        """Clear books from storage and return removed count."""
        self._refresh_from_disk()
        if status is None:
            removed = len(self._cache)
            self._cache = []
            self._persist()
            return removed

        original_len = len(self._cache)
        self._cache = [book for book in self._cache if book.status != status]
        removed = original_len - len(self._cache)
        self._persist()
        return removed

    def delete_book(self, book_id: str) -> bool:
        """Delete a single book by id and return whether it existed."""
        self._refresh_from_disk()
        original_len = len(self._cache)
        self._cache = [book for book in self._cache if book.id != book_id]
        removed = len(self._cache) != original_len
        if removed:
            self._persist()
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
        self.upsert_book(sample)

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
