import asyncio
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import pandas as pd

from biblioforge.models.book import Book, BookStatus
from biblioforge.repositories.book_repository import BookRepository
from biblioforge.services.ai_service import generate_insights
from biblioforge.services.crawling_service import enrich_book
from biblioforge.services.normalization_service import normalize_title


class PipelineController:
    """Coordinates cleaning, enrichment, AI, and persistence."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        processed_dir = Path(__file__).resolve().parent.parent / "data" / "processed"
        target = storage_path or processed_dir / "books.json"
        approved_target = processed_dir / "approved_books.json"

        self.repository = BookRepository(target)
        self.approved_repository = BookRepository(approved_target)
        self.repository.seed_sample_if_empty()

    def ingest_raw_book(self, raw_title: str, author: Optional[str] = None) -> Book:
        normalized_title = normalize_title(raw_title)
        book = Book(
            raw_title=raw_title,
            normalized_title=normalized_title,
            author=author,
            status=BookStatus.IN_PROGRESS,
        )
        book = asyncio.run(enrich_book(book))
        book = generate_insights(book)
        return self.repository.upsert_book(book)

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

    def ingest_books_from_excel(
        self,
        excel_path: Path,
        title_column: str = "Title",
        author_column: str = "Author",
    ) -> int:
        frame = pd.read_excel(excel_path)
        effective_title_col = title_column if title_column in frame.columns else "Titolo"
        effective_author_col = author_column if author_column in frame.columns else "Autore"

        queued = 0
        for _, row in frame.iterrows():
            title_value = str(row.get(effective_title_col, "")).strip()
            if not title_value:
                continue
            author_value = str(row.get(effective_author_col, "")).strip()
            author = author_value or None
            self.ingest_raw_book(title_value, author)
            queued += 1
        return queued

    def reject_and_retry(self, book_id: str) -> Optional[Book]:
        book = self.repository.get_book(book_id)
        if not book:
            return None

        previous_summary = book.insights.summary if book.insights else None
        regeneration_token = str(uuid4())
        book.reject_attempts = int(book.reject_attempts or 0) + 1

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
