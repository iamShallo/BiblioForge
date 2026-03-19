import json
from pathlib import Path
from typing import List, Optional

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
        try:
            raw = json.loads(self.storage_path.read_text())
        except json.JSONDecodeError:
            return []
        if not isinstance(raw, list):
            return []
        return [self._dict_to_book(item) for item in raw if isinstance(item, dict)]

    def _persist(self) -> None:
        payload = [book.to_dict() for book in self._cache]
        self.storage_path.write_text(json.dumps(payload, indent=2))

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
            openlibrary_key="OL82563W",
            first_publish_year=1980,
            edition_count=120,
            average_rating=4.5,
            ratings_count=24000,
            positive_ratio=0.913,
            review_samples=[
                ReviewSample(
                    reviewer="Elena",
                    rating=4.8,
                    text="Dense mystery that blends theology and politics in a medieval abbey.",
                ),
                ReviewSample(
                    reviewer="Luca",
                    rating=4.6,
                    text="Eco keeps tension high while exploring knowledge, power, and faith.",
                ),
            ],
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
        return Book(
            raw_title=data.get("raw_title", ""),
            normalized_title=data.get("normalized_title", ""),
            author=data.get("author"),
            fetched_summary=data.get("fetched_summary"),
            summary_source=data.get("summary_source"),
            catalog_ean=data.get("catalog_ean"),
            catalog_publisher=data.get("catalog_publisher"),
            catalog_quantity=data.get("catalog_quantity"),
            catalog_price=data.get("catalog_price"),
            isbn=data.get("isbn"),
            isbn_10=data.get("isbn_10"),
            published_date=data.get("published_date"),
            publication_year=data.get("publication_year"),
            pages=data.get("pages"),
            cover_url=data.get("cover_url"),
            publisher=data.get("publisher"),
            categories=list(data.get("categories", [])),
            subtitle=data.get("subtitle"),
            language=data.get("language"),
            print_type=data.get("print_type"),
            info_link=data.get("info_link"),
            preview_link=data.get("preview_link"),
            canonical_volume_link=data.get("canonical_volume_link"),
            openlibrary_key=data.get("openlibrary_key"),
            first_publish_year=data.get("first_publish_year"),
            edition_count=data.get("edition_count"),
            average_rating=data.get("average_rating"),
            ratings_count=int(data.get("ratings_count", 0) or 0),
            positive_ratio=data.get("positive_ratio"),
            review_samples=reviews,
            discarded_information_examples=list(data.get("discarded_information_examples", [])),
            insights=insights,
            reject_attempts=int(data.get("reject_attempts", 0) or 0),
            status=BookRepository._normalize_status(data.get("status")),
            id=data.get("id"),
        )
