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
        return [self._dict_to_book(item) for item in raw]

    def _persist(self) -> None:
        payload = [book.to_dict() for book in self._cache]
        self.storage_path.write_text(json.dumps(payload, indent=2))

    def list_books(self, status: Optional[BookStatus] = None) -> List[Book]:
        if status is None:
            return list(self._cache)
        return [b for b in self._cache if b.status == status]

    def get_book(self, book_id: str) -> Optional[Book]:
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
        book = self.get_book(book_id)
        if not book:
            return None
        book.status = status
        self._persist()
        return book

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
            maturity_rating="NOT_MATURE",
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
        reviews = [ReviewSample(**item) for item in data.get("review_samples", [])]
        rejected = [TransparencyNote(**item) for item in data.get("insights", {}).get("rejected_information", [])]
        insights_data = data.get("insights")
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
            maturity_rating=data.get("maturity_rating"),
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
            insights=insights,
            reject_attempts=int(data.get("reject_attempts", 0) or 0),
            status=BookRepository._normalize_status(data.get("status")),
            id=data.get("id"),
        )
