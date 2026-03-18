from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional
from uuid import uuid4


class BookStatus(str, Enum):
    TO_CLEAN = "to_clean"
    IN_PROGRESS = "in_progress"
    TO_APPROVE = "to_approve"
    APPROVED = "approved"


@dataclass
class ReviewSample:
    reviewer: str
    rating: float
    text: str


@dataclass
class TransparencyNote:
    reason: str
    detail: str


@dataclass
class BookInsights:
    summary: str
    tags: List[str] = field(default_factory=list)
    rejected_information: List[TransparencyNote] = field(default_factory=list)


@dataclass
class Book:
    raw_title: str
    normalized_title: str
    author: Optional[str] = None
    fetched_summary: Optional[str] = None
    summary_source: Optional[str] = None
    isbn: Optional[str] = None
    isbn_10: Optional[str] = None
    published_date: Optional[str] = None
    publication_year: Optional[int] = None
    pages: Optional[int] = None
    cover_url: Optional[str] = None
    publisher: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    subtitle: Optional[str] = None
    language: Optional[str] = None
    maturity_rating: Optional[str] = None
    print_type: Optional[str] = None
    info_link: Optional[str] = None
    preview_link: Optional[str] = None
    canonical_volume_link: Optional[str] = None
    openlibrary_key: Optional[str] = None
    first_publish_year: Optional[int] = None
    edition_count: Optional[int] = None
    average_rating: Optional[float] = None
    ratings_count: int = 0
    positive_ratio: Optional[float] = None
    review_samples: List[ReviewSample] = field(default_factory=list)
    insights: Optional[BookInsights] = None
    reject_attempts: int = 0
    status: BookStatus = BookStatus.TO_CLEAN
    id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict:
        """Serialize nested dataclasses to plain dicts."""
        return asdict(self)
