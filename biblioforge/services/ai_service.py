"""Gemini-powered insights generation with Pydantic validation and fallback."""

import json
import os
import re
from typing import List, Optional
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError, Field

from biblioforge.models.book import Book, BookInsights, BookStatus, TransparencyNote
from biblioforge.services.normalization_service import normalize_title


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


class CatalogNormalizationPayload(BaseModel):
    title: str
    author: Optional[str] = None
    publisher: Optional[str] = None


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _summary_is_acceptable(summary: str) -> bool:
    lowered = (summary or "").lower()
    forbidden_markers = [
        "author:",
        "year:",
        "pages:",
        "isbn:",
        "reader excerpts mention",
        "is presented with the available catalog metadata",
        "revision note [",
    ]
    if any(marker in lowered for marker in forbidden_markers):
        return False

    spoilers = ["ending", "killer is", "turns out", "in the final", "identity revealed"]
    if any(token in lowered for token in spoilers):
        return False

    words = _word_count(summary)
    return 45 <= words <= 180


def _trim_to_word_limit(text: str, max_words: int) -> str:
    words = re.findall(r"\S+", text or "")
    if len(words) <= max_words:
        return (text or "").strip()
    return " ".join(words[:max_words]).strip()


def _sanitize_summary_source_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    # Remove very common promo/noise fragments from metadata descriptions.
    promo_patterns = [
        r"(?i)\b(nuova edizione speciale|edizione speciale|fenomeno editoriale)\b",
        r"(?i)\b([0-9]+\s*(milioni|mila)\s+di\s+copie\s+vendute)\b",
        r"(?i)\b(bestseller(?:\s+internazionale)?)\b",
        r"(?i)\b(per\s+il\s+\w+\s+anniversario[^\.,;:]*)",
    ]
    for pattern in promo_patterns:
        cleaned = re.sub(pattern, "", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
    return cleaned


def _build_story_summary(book: Book) -> str:
    title = book.normalized_title or book.raw_title
    source = _sanitize_summary_source_text(book.fetched_summary or "")

    spoiler_markers = [
        "killer is",
        "turns out",
        "ending",
        "finale",
        "twist",
        "identity revealed",
        "muore",
        "assassino",
        "colpo di scena finale",
        "si scopre che",
    ]

    if source:
        # Keep only early, spoiler-safe sentences to preserve story setup.
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", source) if p.strip()]
        kept: List[str] = []
        for part in parts:
            lower_part = part.lower()
            if any(marker in lower_part for marker in spoiler_markers):
                continue
            kept.append(part)
            if len(kept) >= 3:
                break

        candidate = " ".join(kept).strip() if kept else source
        candidate = _trim_to_word_limit(candidate, 120)
        if candidate and candidate[-1] not in ".!?":
            candidate += "."
        if _word_count(candidate) >= 25:
            return candidate

    # If no sufficient data was found, return the message about insufficient description
    # instead of the generic template summary
    return "Non è stata trovata una descrizione accurata per questo libro"


def _tags_are_acceptable(tags: List[str]) -> bool:
    clean = [t.strip() for t in tags if str(t).strip()]
    if len(clean) < 4:
        return False
    if len(clean) > 10:
        return False
    # Avoid low-quality one-word noise tags.
    very_short = [t for t in clean if len(t) <= 2]
    if very_short:
        return False
    return True


def _derive_tags(book: Book) -> List[str]:
    candidates: List[str] = []
    if getattr(book, "categories", None):
        candidates.extend(book.categories)

    # Prefer broad editorial tags over author names.
    if book.publication_year and book.publication_year < 1980:
        candidates.append("20th Century")
    if book.publication_year and book.publication_year >= 2000:
        candidates.append("Contemporary")
    if (book.positive_ratio or 0) >= 0.85:
        candidates.append("Highly Rated")
    if book.publication_year and book.publication_year < 2000:
        candidates.append("Classic")

    if book.fetched_summary:
        text = book.fetched_summary.lower()
        keyword_tags = {
            "murder": "Mystery",
            "detective": "Investigation",
            "history": "Historical Fiction",
            "war": "War",
            "romance": "Romance",
            "science": "Science",
            "fantasy": "Fantasy",
            "crime": "Crime",
            "politic": "Political",
            "religion": "Religion",
            "philosoph": "Philosophy",
            "court": "Legal",
            "family": "Family Saga",
            "magic": "Magic",
            "coming-of-age": "Coming of Age",
        }
        for keyword, tag in keyword_tags.items():
            if keyword in text:
                candidates.append(tag)

    if book.review_samples:
        review_text = " ".join(sample.text for sample in book.review_samples).lower()
        review_map = {
            "slow": "Slow Burn",
            "twist": "Twisty",
            "atmosphere": "Atmospheric",
            "character": "Character-Driven",
            "world": "World-Building",
            "epic": "Epic",
            "political": "Political Intrigue",
            "court": "Court Politics",
            "magic": "Magic System",
            "adventure": "Adventure",
        }
        for keyword, tag in review_map.items():
            if keyword in review_text:
                candidates.append(tag)

    if book.pages and book.pages >= 500:
        candidates.append("Long Read")

    fallback_defaults = ["Character-Driven", "Atmospheric", "High Stakes", "Plot-Driven"]
    candidates.extend(fallback_defaults)

    ordered = []
    seen = set()
    for item in candidates:
        clean = str(item).strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(clean)
    return ordered[:8]


def _derive_rejected_information(book: Book) -> List[TransparencyNote]:
    rejected: List[TransparencyNote] = []
    discarded_examples: List[str] = list(getattr(book, "discarded_information_examples", []) or [])
    if not book.review_samples:
        rejected.append(
            TransparencyNote(
                reason="No direct user reviews",
                detail="Excluded reader-opinion claims because no review samples were available.",
            )
        )
    if not book.isbn:
        rejected.append(
            TransparencyNote(
                reason="Missing ISBN",
                detail="Dropped edition-specific details due to missing ISBN metadata.",
            )
        )
    if not book.publication_year:
        rejected.append(
            TransparencyNote(
                reason="Missing publication date",
                detail="Removed historical placement claims that require a verified publication year.",
            )
        )
    if not book.fetched_summary:
        rejected.append(
            TransparencyNote(
                reason="Insufficient synopsis",
                detail="Avoided plot-specific statements because no trusted summary was fetched.",
            )
        )
    if discarded_examples:
        for example in discarded_examples[:2]:
            rejected.append(
                TransparencyNote(
                    reason="Promotional or noisy source removed",
                    detail=f"Filtered low-quality source snippet. Removed example: \"{example}\"",
                )
            )
    if not rejected:
        rejected.append(
            TransparencyNote(
                reason="Marketing language filtered",
                detail="Removed promotional wording to keep the report factual and source-grounded.",
            )
        )
    return rejected[:6]


def _fallback_insights(book: Book) -> BookInsights:
    summary_text = _build_story_summary(book)

    return BookInsights(
        summary=summary_text,
        tags=_derive_tags(book),
        rejected_information=_derive_rejected_information(book),
    )


def _build_prompt(book: Book, regeneration_token: Optional[str] = None) -> str:
    rating_line = f"Positive ratio: {book.positive_ratio}" if book.positive_ratio else ""
    return (
        "You are generating an editorial report for a book. "
        "Return JSON with keys: summary (string), tags (array of strings), "
        "rejected_information (array of objects with reason and detail). "
        "Be concise; avoid opinions not grounded in provided inputs.\n"
        "Summary constraints: 70-140 words, spoiler-free, no ending reveal, no killer reveal, no final twist reveal.\n"
        "Write summary as a story synopsis focused on setup, central conflict, characters, and early narrative arc.\n"
        "Use only the Crawler/API Summary as factual source for plot information.\n"
        "Do not include, quote, or paraphrase user reviews in the summary.\n"
        "Keep the same language used by the source metadata/reviews whenever possible.\n"
        "Tag constraints: provide 5 to 8 high-quality tags (genre, tone, themes, audience, pacing), not author names.\n"
        "Do not append metadata fields like Author/Year/ISBN/Pages in the summary.\n"
        "Use fresh wording and sentence structure for each generation.\n"
        f"Regeneration token: {regeneration_token or 'initial-pass'}\n\n"
        f"Reject attempts so far: {book.reject_attempts}\n"
        f"Title: {book.normalized_title or book.raw_title}\n"
        f"Author: {book.author or 'Unknown'}\n"
        f"ISBN: {book.isbn or '-'}\n"
        f"Year: {book.publication_year or '-'}\n"
        f"Pages: {book.pages or '-'}\n"
        f"{rating_line}\n"
        f"Crawler/API Summary: {book.fetched_summary or '-'}\n"
        f"Crawler/API Source: {book.summary_source or '-'}\n"
        "JSON only, no markdown, no prose."
    )


def _enforce_summary_variation(summary: str, regeneration_token: Optional[str]) -> str:
    if not regeneration_token:
        return summary
    lowered = (summary or "").lower()
    italian_hints = [
        " il ",
        " lo ",
        " la ",
        " gli ",
        " che ",
        " con ",
        " senza ",
        " trama",
        " personaggi",
        " atmosfera",
    ]
    is_italian = any(hint in f" {lowered} " for hint in italian_hints)

    if is_italian:
        variants = [
            "L'attenzione resta su temi, atmosfera e posta in gioco, senza rivelare snodi decisivi.",
            "La descrizione mette al centro tono e conflitto iniziale, evitando rivelazioni cruciali.",
            "Il riassunto privilegia ambientazione e tensione narrativa, mantenendo riservati i passaggi chiave.",
        ]
    else:
        variants = [
            "The narrative emphasis stays on themes, atmosphere, and stakes without revealing decisive turns.",
            "The description highlights tone and central conflict while keeping major revelations undisclosed.",
            "The abstract prioritizes setting and tension, avoiding spoilers about late-story outcomes.",
        ]
    idx = abs(hash(regeneration_token)) % len(variants)
    base = summary.strip()
    if base and base[-1] not in ".!?":
        base += "."
    return f"{base} {variants[idx]}"


def _parse_json_object(text: str) -> dict:
    payload_text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", payload_text, re.DOTALL)
    if fenced:
        payload_text = fenced.group(1)
    if payload_text and payload_text[0] != "{":
        first = payload_text.find("{")
        last = payload_text.rfind("}")
        if first != -1 and last != -1 and first < last:
            payload_text = payload_text[first:last + 1]
    return json.loads(payload_text)


def _parse_gemini_response(text: str) -> BookInsights:
    data = _parse_json_object(text)
    payload = InsightsPayload(**data)
    rejected = [TransparencyNote(**item.dict()) for item in payload.rejected_information]
    return BookInsights(
        summary=payload.summary,
        tags=payload.tags,
        rejected_information=rejected,
    )


def _simple_cleanup_title(raw_title: str, raw_author: Optional[str] = None) -> str:
    parsed_title, parsed_author = _extract_embedded_author(raw_title, raw_author)
    text = (raw_title or "").strip()
    text = re.sub(r"\s+", " ", text)
    if parsed_title:
        text = parsed_title
    text = normalize_title(text, parsed_author or raw_author)
    return text.strip()


def _simple_cleanup_author(raw_author: Optional[str]) -> Optional[str]:
    if raw_author is None:
        return None
    text = str(raw_author).strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)

    # Catalog rows sometimes append publisher/store names after author, e.g.
    # "George R. R. Martin, Mondadori". Keep only person-like chunks.
    chunks = [chunk.strip() for chunk in re.split(r"[,;|/]", text) if chunk.strip()]
    if len(chunks) > 1:
        person_chunks = [chunk for chunk in chunks if _looks_like_person_name(chunk)]
        if person_chunks:
            if len(person_chunks) >= 2 and all(_looks_like_person_name(chunk) for chunk in chunks[:2]):
                # Preserve common "Surname, Name" forms.
                text = f"{chunks[0]}, {chunks[1]}"
            else:
                text = person_chunks[0]

    return text


def _looks_like_person_name(text: str) -> bool:
    if not text:
        return False
    if any(ch.isdigit() for ch in text):
        return False

    lowered = text.lower()
    forbidden = ["edizione", "edition", "volume", "vol", "deluxe", "collector", "special"]
    if any(token in lowered for token in forbidden):
        return False

    stopwords = {"del", "della", "dello", "dei", "degli", "di", "da", "e", "ed", "al", "alla"}

    tokens = [t for t in re.split(r"\s+", text.strip()) if t]
    if len(tokens) < 2 or len(tokens) > 8:
        return False
    if any(token.strip(".,'").lower() in stopwords for token in tokens):
        return False

    def _token_is_name_like(token: str) -> bool:
        stripped = token.strip(".,'")
        if not stripped:
            return False
        # Initials such as "R." are allowed.
        if re.fullmatch(r"[A-ZÀ-ÖØ-Ý]\.?", stripped):
            return True
        return bool(re.fullmatch(r"[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ]+", stripped))

    if not all(_token_is_name_like(token) for token in tokens):
        return False

    alpha_tokens = [t for t in tokens if re.search(r"[a-zA-Z]", t)]
    if len(alpha_tokens) < 2:
        return False
    return True


def _extract_embedded_author(raw_title: str, raw_author: Optional[str] = None) -> tuple[str, Optional[str]]:
    title_text = (raw_title or "").strip()
    explicit_author = _simple_cleanup_author(raw_author)
    if explicit_author:
        return title_text, explicit_author

    if not title_text:
        return "", None

    # Match common catalog formats like: "Title, Author" or "Title - Author".
    split_patterns = [
        r"^(?P<title>.+?)\s*,\s*(?P<author>[^,]+)$",
        r"^(?P<title>.+?)\s+-\s+(?P<author>.+)$",
        r"^(?P<title>.+?)\s+[\u2013\u2014]\s+(?P<author>.+)$",
    ]
    for pattern in split_patterns:
        match = re.match(pattern, title_text)
        if not match:
            continue
        candidate_title = re.sub(r"\s+", " ", match.group("title")).strip(" -_\t\n,;")
        candidate_author = _simple_cleanup_author(match.group("author"))
        if candidate_author and _looks_like_person_name(candidate_author) and candidate_title:
            return candidate_title, candidate_author

    # Fallback for noisy rows where author is appended at the end without separators.
    tokens = [token for token in re.split(r"\s+", title_text) if token]
    if len(tokens) >= 4:
        for author_len in [4, 3, 2]:
            if len(tokens) <= author_len + 1:
                continue
            candidate_author = _simple_cleanup_author(" ".join(tokens[-author_len:]))
            candidate_title = re.sub(r"\s+", " ", " ".join(tokens[:-author_len])).strip(" -_\t\n,;")
            if candidate_author and _looks_like_person_name(candidate_author) and candidate_title:
                return candidate_title, candidate_author

    return title_text, None


def normalize_catalog_entry(
    raw_title: str,
    raw_author: Optional[str] = None,
    raw_publisher: Optional[str] = None,
) -> dict:
    """Normalize noisy catalog fields using Gemini, with deterministic fallback."""
    parsed_title, parsed_author = _extract_embedded_author(raw_title, raw_author)
    fallback = {
        "title": _simple_cleanup_title(parsed_title or raw_title, parsed_author or raw_author),
        "author": _simple_cleanup_author(parsed_author or raw_author),
        "publisher": _simple_cleanup_author(raw_publisher),
        "source": "rule_based",
    }

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return fallback

    prompt = (
        "Normalize the following catalog row for book lookup. "
        "Fix spelling and OCR errors but do not invent missing data. "
        "If title contains author names, remove author names from title and keep them in author only. "
        "If title contains edition labels (e.g., deluxe, collector, special, vol., ediz.), remove them. "
        "Return strictly JSON with keys: title, author, publisher. "
        "Keep original language and do not translate.\n\n"
        f"Raw title: {raw_title or '-'}\n"
        f"Raw author: {parsed_author or raw_author or '-'}\n"
        f"Raw publisher: {raw_publisher or '-'}\n"
    )

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                GEMINI_URL,
                params={"key": api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "topP": 0.8,
                    },
                },
            )
            resp.raise_for_status()
            candidates = resp.json().get("candidates", [])
            content: Optional[str] = None
            if candidates:
                content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not content:
                return fallback

            parsed = CatalogNormalizationPayload(**_parse_json_object(content))
            title = _simple_cleanup_title(parsed.title, parsed.author or parsed_author or raw_author)
            author = _simple_cleanup_author(parsed.author or parsed_author or raw_author)
            publisher = _simple_cleanup_author(parsed.publisher)
            if not title:
                return fallback
            return {
                "title": title,
                "author": author,
                "publisher": publisher,
                "source": "gemini",
            }
    except (httpx.HTTPError, ValidationError, json.JSONDecodeError):
        return fallback


def generate_insights(
    book: Book,
    regeneration_token: Optional[str] = None,
    previous_summary: Optional[str] = None,
) -> Book:
    """Call Gemini; fall back to local heuristics on error."""
    api_key = os.getenv("GEMINI_API_KEY")
    insights = None
    if api_key:
        max_attempts = 3
        with httpx.Client(timeout=20) as client:
            for attempt in range(max_attempts):
                try:
                    token_suffix = f"{regeneration_token or 'run'}-a{attempt + 1}"
                    prompt = _build_prompt(book, regeneration_token=token_suffix)
                    resp = client.post(
                        GEMINI_URL,
                        params={"key": api_key},
                        json={
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {
                                "temperature": 0.9,
                                "topP": 0.95,
                            },
                        },
                    )
                    resp.raise_for_status()
                    candidates = resp.json().get("candidates", [])
                    content: Optional[str] = None
                    if candidates:
                        content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if not content:
                        continue

                    candidate = _parse_gemini_response(content)
                    if not _summary_is_acceptable(candidate.summary):
                        continue
                    if not _tags_are_acceptable(candidate.tags):
                        candidate.tags = _derive_tags(book)
                    insights = candidate
                    break
                except (httpx.HTTPError, ValidationError, json.JSONDecodeError):
                    insights = None
                    continue

    if not insights:
        insights = _fallback_insights(book)
        if not _summary_is_acceptable(insights.summary):
            insights.summary = _build_story_summary(book)
        if not _tags_are_acceptable(insights.tags):
            insights.tags = _derive_tags(book)

    if previous_summary and insights.summary.strip() == previous_summary.strip():
        token = regeneration_token or str(uuid4())
        insights.summary = _enforce_summary_variation(insights.summary, token)
        if not _summary_is_acceptable(insights.summary):
            insights.summary = _build_story_summary(book)

    book.insights = insights
    book.status = BookStatus.TO_APPROVE
    return book
