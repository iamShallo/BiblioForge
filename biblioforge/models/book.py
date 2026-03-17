from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional
from uuid import uuid4


class BookStatus(str, Enum):
    RAW = "raw"
    CLEANED = "cleaned"
    ENRICHED = "enriched"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


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
    isbn: Optional[str] = None
    publication_year: Optional[int] = None
    pages: Optional[int] = None
    cover_url: Optional[str] = None
    positive_ratio: Optional[float] = None
    review_samples: List[ReviewSample] = field(default_factory=list)
    insights: Optional[BookInsights] = None
    status: BookStatus = BookStatus.RAW
    id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict:
        """Serialize nested dataclasses to plain dicts."""
        return asdict(self)
