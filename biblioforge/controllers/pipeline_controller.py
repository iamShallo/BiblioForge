import asyncio
from pathlib import Path
from typing import List, Optional

from biblioforge.models.book import Book, BookStatus
from biblioforge.repositories.book_repository import BookRepository
from biblioforge.services.ai_service import generate_insights
from biblioforge.services.crawling_service import enrich_book
from biblioforge.services.normalization_service import normalize_title


class PipelineController:
    """Coordinates cleaning, enrichment, AI, and persistence."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        target = storage_path or Path(__file__).resolve().parent.parent / "data" / "processed" / "books.json"
        self.repository = BookRepository(target)
        self.repository.seed_sample_if_empty()

    def ingest_raw_book(self, raw_title: str, author: Optional[str] = None) -> Book:
        normalized_title = normalize_title(raw_title)
        book = Book(
            raw_title=raw_title,
            normalized_title=normalized_title,
            author=author,
            status=BookStatus.CLEANED,
        )
        book = asyncio.run(enrich_book(book))
        book = generate_insights(book)
        return self.repository.upsert_book(book)

    def list_pending(self) -> List[Book]:
        return self.repository.list_books(BookStatus.PENDING_REVIEW)

    def approve(self, book_id: str) -> Optional[Book]:
        return self.repository.update_status(book_id, BookStatus.APPROVED)

    def reject_and_retry(self, book_id: str) -> Optional[Book]:
        book = self.repository.update_status(book_id, BookStatus.RAW)
        return book

    def get(self, book_id: str) -> Optional[Book]:
        return self.repository.get_book(book_id)
