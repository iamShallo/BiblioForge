import asyncio
import random
from typing import List, Optional

from biblioforge.models.book import Book, BookStatus, ReviewSample


async def fetch_cover_url(normalized_title: str) -> str:
    """Stub that would call Google Books or OpenLibrary."""
    seed = abs(hash(normalized_title)) % 10
    return (
        f"https://picsum.photos/seed/{seed}/320/480"
    )


async def fetch_metadata(normalized_title: str, author: Optional[str]) -> dict:
    """Return minimal metadata; replace with real API calls."""
    return {
        "publication_year": 2010,
        "pages": random.choice([320, 355, 400]),
        "isbn": f"31213663{random.randint(100,999)}",
        "cover_url": await fetch_cover_url(normalized_title),
    }


async def fetch_review_samples(normalized_title: str) -> List[ReviewSample]:
    """Return lightweight review samples."""
    templates = [
        (
            "Alex",
            4.7,
            "Smart pacing that balances atmosphere and clues without losing depth.",
        ),
        (
            "Sam",
            4.5,
            "Blends history and investigation with approachable language.",
        ),
    ]
    await asyncio.sleep(0)  # keep signature async-friendly
    return [ReviewSample(reviewer=name, rating=rating, text=text) for name, rating, text in templates]


async def enrich_book(book: Book) -> Book:
    """Attach metadata and reviews to a book."""
    metadata = await fetch_metadata(book.normalized_title, book.author)
    reviews = await fetch_review_samples(book.normalized_title)
    book.isbn = metadata.get("isbn")
    book.publication_year = metadata.get("publication_year")
    book.pages = metadata.get("pages")
    book.cover_url = metadata.get("cover_url")
    book.review_samples = reviews
    book.positive_ratio = round(random.uniform(0.7, 0.96), 3)
    book.status = BookStatus.ENRICHED
    return book
