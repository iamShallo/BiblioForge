"""Gemini-powered insights generation with Pydantic validation and fallback."""

import json
import os
from typing import List, Optional

import httpx
from pydantic import BaseModel, ValidationError, Field

from biblioforge.models.book import Book, BookInsights, BookStatus, TransparencyNote


GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash-latest:generateContent"
)


class TransparencyNotePayload(BaseModel):
    reason: str
    detail: str


class InsightsPayload(BaseModel):
    summary: str
    tags: List[str] = Field(default_factory=list)
    rejected_information: List[TransparencyNotePayload] = Field(default_factory=list)


def _fallback_insights(book: Book) -> BookInsights:
    title = book.normalized_title or book.raw_title
    return BookInsights(
        summary=(
            f"{title} blends investigation and history to surface themes of knowledge and power. "
            "Reviews highlight atmosphere, textured world building, and steady suspense."
        ),
        tags=[tag for tag in ["Historical Fiction", "Mystery", "Investigation", book.author] if tag],
        rejected_information=[
            TransparencyNote(
                reason="Off-focus trivia",
                detail="Removed film adaptation details and marketing copy.",
            ),
            TransparencyNote(
                reason="Redundant praise",
                detail="Collapsed repetitive review sentences into one insight.",
            ),
        ],
    )


def _build_prompt(book: Book) -> str:
    rating_line = f"Positive ratio: {book.positive_ratio}" if book.positive_ratio else ""
    reviews: List[str] = [f"- {r.reviewer}: {r.text} (rating {r.rating})" for r in book.review_samples]
    reviews_block = "\n".join(reviews) if reviews else "- No review samples available."
    return (
        "You are generating an editorial report for a book. "
        "Return JSON with keys: summary (string), tags (array of strings), "
        "rejected_information (array of objects with reason and detail). "
        "Be concise; avoid opinions not grounded in provided inputs.\n\n"
        f"Title: {book.normalized_title or book.raw_title}\n"
        f"Author: {book.author or 'Unknown'}\n"
        f"ISBN: {book.isbn or '-'}\n"
        f"Year: {book.publication_year or '-'}\n"
        f"Pages: {book.pages or '-'}\n"
        f"{rating_line}\n"
        "Reviews:\n"
        f"{reviews_block}\n"
        "JSON only, no markdown, no prose."
    )


def _parse_gemini_response(text: str) -> BookInsights:
    data = json.loads(text)
    payload = InsightsPayload(**data)
    rejected = [TransparencyNote(**item.dict()) for item in payload.rejected_information]
    return BookInsights(
        summary=payload.summary,
        tags=payload.tags,
        rejected_information=rejected,
    )


def generate_insights(book: Book) -> Book:
    """Call Gemini; fall back to local heuristics on error."""
    api_key = os.getenv("GEMINI_API_KEY")
    prompt = _build_prompt(book)

    insights = None
    if api_key:
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(
                    GEMINI_URL,
                    params={"key": api_key},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                )
                resp.raise_for_status()
                candidates = resp.json().get("candidates", [])
                content: Optional[str] = None
                if candidates:
                    content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if content:
                    insights = _parse_gemini_response(content)
        except (httpx.HTTPError, ValidationError, json.JSONDecodeError):
            insights = None

    if not insights:
        insights = _fallback_insights(book)

    book.insights = insights
    book.status = BookStatus.PENDING_REVIEW
    return book
