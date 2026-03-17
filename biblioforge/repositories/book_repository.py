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

    def seed_sample_if_empty(self) -> None:
        if self._cache:
            return
        sample = Book(
            raw_title="Il Nome della Rosa - Umberto Eco",
            normalized_title="The Name of the Rose",
            author="Umberto Eco",
            isbn="312136632299",
            publication_year=2010,
            pages=355,
            cover_url=(
                "https://images-na.ssl-images-amazon.com/images/I/51U0gB02cDL._SX331_BO1,204,203,200_.jpg"
            ),
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
            status=BookStatus.PENDING_REVIEW,
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
            isbn=data.get("isbn"),
            publication_year=data.get("publication_year"),
            pages=data.get("pages"),
            cover_url=data.get("cover_url"),
            positive_ratio=data.get("positive_ratio"),
            review_samples=reviews,
            insights=insights,
            status=BookStatus(data.get("status", BookStatus.RAW)),
            id=data.get("id"),
        )
