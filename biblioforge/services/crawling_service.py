"""Google Books-backed crawling and enrichment, with Goodreads HTML scrape for ratings."""

import asyncio
import difflib
import html
import json
import os
import re
import unicodedata
from typing import List, Optional, Tuple
from urllib.parse import quote_plus

import httpx

from biblioforge.models.book import Book, BookStatus, ReviewSample
from biblioforge.services.normalization_service import normalize_title


GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
GOODREADS_SEARCH_URL = "https://www.goodreads.com/search"
OPENLIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
AMAZON_IT_SEARCH_URL = "https://www.amazon.it/s"


def _normalize_for_match(text: Optional[str]) -> str:
    if not text:
        return ""
    lowered = str(text).strip().lower()
    lowered = unicodedata.normalize("NFKD", lowered)
    lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _title_similarity(left: Optional[str], right: Optional[str]) -> float:
    l_norm = _normalize_for_match(left)
    r_norm = _normalize_for_match(right)
    if not l_norm or not r_norm:
        return 0.0
    ratio = difflib.SequenceMatcher(None, l_norm, r_norm).ratio()

    # Token overlap helps recover from swapped words and OCR-like noise.
    l_tokens = set(l_norm.split())
    r_tokens = set(r_norm.split())
    if not l_tokens or not r_tokens:
        return ratio
    overlap = len(l_tokens & r_tokens) / max(len(l_tokens), len(r_tokens))
    return max(ratio, overlap)


def _compute_ratio(book: Book) -> Optional[float]:
    """Derive positive ratio deterministically from available ratings."""
    if book.average_rating is not None:
        return round(min(max(book.average_rating / 5, 0), 1), 3)
    return None


def _compute_ratio_from_reviews(samples: List[ReviewSample]) -> Optional[float]:
    """Compute ratio from collected review ratings when API ratings are missing."""
    ratings = [s.rating for s in samples if isinstance(getattr(s, "rating", None), (int, float))]
    if not ratings:
        return None
    avg = sum(ratings) / len(ratings)
    return round(min(max(avg / 5, 0), 1), 3)


def _deterministic_float(book: Book, low: float, high: float) -> float:
    seed = abs(hash(book.normalized_title or book.raw_title)) % 1000
    return low + (seed / 1000.0) * (high - low)


def _deterministic_int(book: Book, low: int, high: int) -> int:
    seed = abs(hash(book.normalized_title or book.raw_title))
    return low + (seed % (high - low + 1))


def _pick_best_google_books_match(items: List[dict], normalized_title: str, author: Optional[str]) -> dict:
    if not items:
        return {}

    author_norm = _normalize_for_match(author)
    best_item = None
    best_score = -1.0

    for item in items:
        volume = item.get("volumeInfo", {})
        candidate_title = volume.get("title")
        score = _title_similarity(normalized_title, candidate_title)

        candidate_authors = volume.get("authors", [])
        if isinstance(candidate_authors, list):
            author_blob = " ".join(str(a) for a in candidate_authors)
        else:
            author_blob = str(candidate_authors or "")
        candidate_author_norm = _normalize_for_match(author_blob)

        if author_norm and candidate_author_norm:
            if author_norm in candidate_author_norm or candidate_author_norm in author_norm:
                score += 0.18
            else:
                score += 0.08 * _title_similarity(author_norm, candidate_author_norm)

        if score > best_score:
            best_score = score
            best_item = item

    # Keep false matches low when queries are very noisy.
    if best_score < 0.42:
        return {}
    return best_item or {}


def _normalize_catalog_code(code: Optional[str]) -> str:
    if not code:
        return ""
    compact = re.sub(r"[^0-9Xx]", "", str(code)).upper()
    return compact


async def _fetch_google_books(
    normalized_title: str,
    author: Optional[str],
    publisher: Optional[str] = None,
    catalog_ean: Optional[str] = None,
) -> dict:
    strict_query_parts = [f'intitle:"{normalized_title}"']
    if author:
        strict_query_parts.append(f'inauthor:"{author}"')
    if publisher:
        strict_query_parts.append(f'inpublisher:"{publisher}"')

    relaxed_query_parts = [f"intitle:{normalized_title}"]
    if author:
        relaxed_query_parts.append(f"inauthor:{author}")
    if publisher:
        relaxed_query_parts.append(f"inpublisher:{publisher}")

    fallback_query = f"{normalized_title} {author or ''} {publisher or ''}".strip()

    api_key = os.getenv("GOOGLE_BOOKS_API_KEY")

    async with httpx.AsyncClient(timeout=15) as client:
        common_params = {"orderBy": "relevance"}
        if api_key:
            common_params["key"] = api_key

        # Emergency exact lookup by ISBN/EAN when title/author are too noisy.
        normalized_code = _normalize_catalog_code(catalog_ean)
        if normalized_code:
            code_resp = await client.get(
                GOOGLE_BOOKS_URL,
                params={
                    **common_params,
                    "q": f"isbn:{normalized_code}",
                    "maxResults": 5,
                },
            )
            code_resp.raise_for_status()
            code_items = code_resp.json().get("items", [])
            code_pick = _pick_best_google_books_match(code_items, normalized_title, author)
            if code_pick:
                return code_pick
            if code_items:
                return code_items[0]

        all_items: List[dict] = []
        seen_ids = set()

        queries = [
            (" ".join(strict_query_parts), 6),
            (fallback_query or normalized_title, 15),
        ]
        if author:
            # Only use relaxed field query when author is known; without author it is too noisy.
            queries.append((" ".join(relaxed_query_parts), 12))

        for query, max_results in queries:
            resp = await client.get(
                GOOGLE_BOOKS_URL,
                params={
                    **common_params,
                    "q": query,
                    "maxResults": max_results,
                },
            )
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                item_id = item.get("id")
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                all_items.append(item)

        return _pick_best_google_books_match(all_items, normalized_title, author)


async def _find_goodreads_book_url(normalized_title: str, author: Optional[str]) -> Optional[str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,it-IT;q=0.8,it;q=0.7",
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        # Prefer title+author resolver to avoid picking the wrong saga volume.
        try:
            resolver_resp = await client.get(
                "https://www.goodreads.com/book/title",
                params={
                    "title": normalized_title,
                    "author": author or "",
                },
            )
            resolver_resp.raise_for_status()
            resolved_url = str(resolver_resp.url)
            if "/book/show/" in resolved_url:
                return resolved_url
        except Exception:
            pass

        params = {"q": f"{normalized_title} {author or ''}".strip()}
        resp = await client.get(GOODREADS_SEARCH_URL, params=params)
        resp.raise_for_status()
        search_html = resp.text

    candidate_matches = re.findall(
        r'<a[^>]*class="[^"]*bookTitle[^"]*"[^>]*href="(/book/show/[^"]+)"[^>]*>(.*?)</a>',
        search_html,
        re.IGNORECASE | re.DOTALL,
    )
    if candidate_matches:
        best_url = None
        best_score = -1.0
        author_norm = _normalize_for_match(author)

        for href, raw_title_html in candidate_matches:
            title_text = _clean_review_text(raw_title_html)
            score = _title_similarity(normalized_title, title_text)

            # Use nearby row content to softly match author when available.
            snippet_pattern = re.escape(href) + r'.{0,600}?class="[^"]*authorName[^"]*"[^>]*>(.*?)</a>'
            snippet_match = re.search(snippet_pattern, search_html, re.IGNORECASE | re.DOTALL)
            if snippet_match and author_norm:
                cand_author = _normalize_for_match(_clean_review_text(snippet_match.group(1)))
                if cand_author and (author_norm in cand_author or cand_author in author_norm):
                    score += 0.2

            if score > best_score:
                best_score = score
                best_url = href

        if best_url and best_score >= 0.35:
            return f"https://www.goodreads.com{best_url}"

    book_link_match = re.search(r'href="(/book/show/[^"]+)"', search_html)
    if not book_link_match:
        return None
    return f"https://www.goodreads.com{book_link_match.group(1)}"


async def search_candidates(
    normalized_title: str,
    author: Optional[str],
    publisher: Optional[str] = None,
    catalog_ean: Optional[str] = None,
    limit: int = 5,
) -> List[dict]:
    """Return a short list of candidate books (title, author, link, cover)."""

    def _candidate_quality(item: dict) -> int:
        volume = item.get("volumeInfo", {}) if isinstance(item, dict) else {}
        score = 0
        if volume.get("pageCount"):
            score += 2
        if volume.get("publishedDate"):
            score += 1
        if volume.get("industryIdentifiers"):
            score += 2
        description = str(volume.get("description") or "").strip()
        if len(description) >= 120:
            score += 2
        elif description:
            score += 1
        if volume.get("categories"):
            score += 1
        if volume.get("publisher"):
            score += 1
        if volume.get("language"):
            score += 1
        if volume.get("imageLinks", {}).get("thumbnail"):
            score += 1
        return score

    def _has_sufficient_google_books_data(item: dict) -> bool:
        volume = item.get("volumeInfo", {}) if isinstance(item, dict) else {}
        title = str(volume.get("title") or "").strip()
        authors = volume.get("authors") or []
        if not isinstance(authors, list):
            authors = [authors]
        author_blob = " ".join(str(a).strip() for a in authors if str(a).strip())

        info_link = str(volume.get("infoLink") or "").strip()
        canonical_link = str(volume.get("canonicalVolumeLink") or "").strip()
        has_link = bool(info_link or canonical_link)

        if not (title and author_blob and has_link):
            return False

        # Avoid weak editions with very sparse metadata.
        quality = _candidate_quality(item)
        if quality < 5:
            return False

        # Require at least one strong bibliographic anchor.
        has_anchor = bool(volume.get("pageCount") or volume.get("industryIdentifiers") or volume.get("description"))
        if not has_anchor:
            return False

        # Keep title close to query and, when provided, keep author close too.
        if _title_similarity(normalized_title, title) < 0.42:
            return False

        # Enforce overlap on meaningful title tokens to avoid off-target books.
        stopwords = {
            "il", "lo", "la", "i", "gli", "le", "un", "una", "uno", "di", "del", "della", "dello",
            "dei", "degli", "delle", "e", "ed", "a", "ad", "da", "in", "con", "per", "su",
            "the", "of", "and", "a", "an", "to", "in", "on", "for",
        }
        query_tokens = {
            t for t in re.findall(r"\w+", _normalize_for_match(normalized_title))
            if len(t) >= 4 and t not in stopwords
        }
        title_tokens = set(re.findall(r"\w+", _normalize_for_match(title)))
        if query_tokens:
            overlap_ratio = len(query_tokens & title_tokens) / len(query_tokens)
            if overlap_ratio < 0.4:
                return False

        if author and _title_similarity(author, author_blob) < 0.30:
            return False

        return True

    results: list[dict] = []
    try:
        item = await _fetch_google_books(normalized_title, author, publisher, catalog_ean)
        if item and _has_sufficient_google_books_data(item):
            results.append(item)

        strict_query_parts = [f'intitle:"{normalized_title}"']
        if author:
            strict_query_parts.append(f'inauthor:"{author}"')
        relaxed_query = f"{normalized_title} {author or ''} {publisher or ''}".strip()

        queries = [
            (" ".join(strict_query_parts), 8),
            (relaxed_query, 12),
        ]

        api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
        async with httpx.AsyncClient(timeout=15) as client:
            common_params = {"orderBy": "relevance"}
            if api_key:
                common_params["key"] = api_key

            seen_ids = set()
            for query, max_results in queries:
                resp = await client.get(
                    GOOGLE_BOOKS_URL,
                    params={**common_params, "q": query, "maxResults": max_results},
                )
                resp.raise_for_status()
                for item in resp.json().get("items", []):
                    if not _has_sufficient_google_books_data(item):
                        continue
                    item_id = item.get("id")
                    if item_id and item_id in seen_ids:
                        continue
                    if item_id:
                        seen_ids.add(item_id)
                    results.append(item)

        def _brief(item: dict) -> dict:
            vol = item.get("volumeInfo", {})
            return {
                "title": vol.get("title"),
                "authors": ", ".join(vol.get("authors", []) or []),
                "published_date": vol.get("publishedDate"),
                "info_link": vol.get("infoLink"),
                "cover_url": vol.get("imageLinks", {}).get("thumbnail"),
            }

        briefed = []
        seen_keys = set()
        for item in results:
            entry = _brief(item)
            key = (entry.get("title") or "", entry.get("authors") or "")
            if key in seen_keys or not entry.get("title"):
                continue
            seen_keys.add(key)
            briefed.append((entry, _candidate_quality(item), _title_similarity(normalized_title, entry.get("title"))))

        # Prefer richer metadata and better title match.
        briefed.sort(key=lambda row: (row[1], row[2]), reverse=True)
        return [row[0] for row in briefed[:limit]]
    except Exception:
        return []


async def _fetch_goodreads_rating(
    normalized_title: str,
    author: Optional[str],
    book_url: Optional[str] = None,
) -> Tuple[Optional[float], int, Optional[str]]:
    """Scrape Goodreads book page to extract average rating, rating count and description."""

    def _to_int(value: Optional[str]) -> int:
        if not value:
            return 0
        digits = re.sub(r"[^0-9]", "", value)
        return int(digits) if digits else 0

    def _extract_from_html(page_html: str) -> Tuple[Optional[float], int, Optional[str]]:
        # JSON-LD is the most stable source when present.
        for match in re.finditer(r"<script type=\"application/ld\+json\">(.*?)</script>", page_html, re.DOTALL):
            try:
                data = json.loads(match.group(1))
                payloads = data if isinstance(data, list) else [data]
                for payload in payloads:
                    if not isinstance(payload, dict):
                        continue
                    agg = payload.get("aggregateRating", {}) or {}
                    rating_val = agg.get("ratingValue")
                    rating_cnt = agg.get("ratingCount") or agg.get("reviewCount") or 0
                    description_val = payload.get("description")
                    rating = float(rating_val) if rating_val is not None else None
                    count = int(rating_cnt) if str(rating_cnt).strip() else 0
                    description = _clean_review_text(description_val) if description_val else None
                    if description and len(description) > 600:
                        description = description[:600].rsplit(" ", 1)[0] + "..."
                    if rating is not None:
                        return rating, count, description
            except Exception:
                continue

        # Goodreads modern layout: "3.68 7,367,301 ratings · 150,700 reviews".
        stats_match = re.search(
            r"([0-5](?:[\.,]\d{1,2})?)\s+([\d\.,]+)\s+ratings?\s*[·\-–]\s*([\d\.,]+)\s+reviews?",
            page_html,
            re.IGNORECASE,
        )
        rating = None
        ratings_count = 0
        if stats_match:
            rating_raw = stats_match.group(1).replace(",", ".")
            try:
                rating = float(rating_raw)
            except Exception:
                rating = None
            ratings_count = _to_int(stats_match.group(2))

        if rating is None:
            # Backup pattern used in some Goodreads variants.
            rating_match = re.search(r"([0-5](?:[\.,]\d{1,2})?)\s+avg\s+rating", page_html, re.IGNORECASE)
            if rating_match:
                try:
                    rating = float(rating_match.group(1).replace(",", "."))
                except Exception:
                    rating = None

        if not ratings_count:
            count_match = re.search(r"([\d\.,]+)\s+ratings", page_html, re.IGNORECASE)
            ratings_count = _to_int(count_match.group(1)) if count_match else 0

        description = None
        desc_match = re.search(r"<meta\s+property=\"og:description\"\s+content=\"(.*?)\"", page_html, re.IGNORECASE)
        if not desc_match:
            desc_match = re.search(r"<meta\s+name=\"description\"\s+content=\"(.*?)\"", page_html, re.IGNORECASE)
        if desc_match:
            description = _clean_review_text(desc_match.group(1))
            if description and len(description) > 600:
                description = description[:600].rsplit(" ", 1)[0] + "..."

        return rating, ratings_count, description

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,it-IT;q=0.8,it;q=0.7",
    }

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        search_html = ""
        resolved_book_url = book_url
        if not resolved_book_url:
            params = {"q": f"{normalized_title} {author or ''}".strip()}
            search_resp = await client.get(GOODREADS_SEARCH_URL, params=params)
            search_resp.raise_for_status()
            search_html = search_resp.text
            book_link_match = re.search(r'href="(/book/show/[^"]+)"', search_html)
            if book_link_match:
                resolved_book_url = f"https://www.goodreads.com{book_link_match.group(1)}"

        if resolved_book_url:
            try:
                book_resp = await client.get(resolved_book_url)
                book_resp.raise_for_status()
                rating, count, description = _extract_from_html(book_resp.text)
                if rating is not None:
                    return rating, count, description
            except Exception:
                pass

        # Fallback: parse search page itself.
        if not search_html:
            params = {"q": f"{normalized_title} {author or ''}".strip()}
            search_resp = await client.get(GOODREADS_SEARCH_URL, params=params)
            search_resp.raise_for_status()
            search_html = search_resp.text
        rating, count, description = _extract_from_html(search_html)
        if rating is not None or description:
            return rating, count, description

    return None, 0, None


async def _fetch_goodreads_user_reviews(
    normalized_title: str,
    author: Optional[str],
    book_url: Optional[str] = None,
) -> List[ReviewSample]:
    """Best-effort extraction of user-facing review snippets from Goodreads pages."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    }

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        resolved_book_url = book_url
        if not resolved_book_url:
            params = {"q": f"{normalized_title} {author or ''}".strip()}
            search_resp = await client.get(GOODREADS_SEARCH_URL, params=params)
            search_resp.raise_for_status()
            search_html = search_resp.text
            book_link_match = re.search(r'href="(/book/show/[^"]+)"', search_html)
            if not book_link_match:
                return []
            resolved_book_url = f"https://www.goodreads.com{book_link_match.group(1)}"

        book_resp = await client.get(resolved_book_url)
        book_resp.raise_for_status()
        page = book_resp.text

    snippets: List[ReviewSample] = []
    seen_snippets = set()

    card_pattern = r'<article class="ReviewCard"[\s\S]*?</article>'
    cards = re.findall(card_pattern, page, re.IGNORECASE)
    for card in cards:
        text_match = re.search(r'data-testid="reviewText"[^>]*>([\s\S]*?)</section>', card, re.IGNORECASE)
        if not text_match:
            text_match = re.search(r'class="ReviewText__content"[^>]*>([\s\S]*?)</span>', card, re.IGNORECASE)
        if not text_match:
            continue

        cleaned = _clean_user_review_text(text_match.group(1))
        if not cleaned or _looks_promotional(cleaned) or _looks_like_synopsis(cleaned):
            continue

        reviewer = "Goodreads User"
        reviewer_match = re.search(r'data-testid="name"[^>]*>[\s\S]*?<a[^>]*>(.*?)</a>', card, re.IGNORECASE)
        if reviewer_match:
            reviewer_clean = _clean_review_text(reviewer_match.group(1))
            if reviewer_clean:
                reviewer = reviewer_clean
        else:
            reviewer_match = re.search(r'aria-label="Review by ([^"]+)"', card, re.IGNORECASE)
            if reviewer_match:
                reviewer_clean = _clean_review_text(reviewer_match.group(1))
                if reviewer_clean:
                    reviewer = reviewer_clean

        rating = None
        rating_match = re.search(r'aria-label="Rating\s*([0-5](?:[\.,]\d+)?)\s*out of 5"', card, re.IGNORECASE)
        if rating_match:
            try:
                rating = float(rating_match.group(1).replace(",", "."))
            except Exception:
                rating = None

        if rating is None:
            continue

        normalized = re.sub(r"\s+", " ", cleaned).strip().lower()
        if normalized in seen_snippets:
            continue
        seen_snippets.add(normalized)

        snippets.append(
            ReviewSample(
                reviewer=reviewer,
                rating=rating,
                text=cleaned[:4000],
            )
        )
        if len(snippets) >= 3:
            return snippets

    return snippets[:3]


async def _fetch_amazon_user_reviews(normalized_title: str, author: Optional[str], max_pages: int = 2) -> List[ReviewSample]:
    """Best-effort extraction of user review snippets from Amazon product pages.

    Note: Amazon may block scraping; failures should not break the pipeline.
    max_pages controls pagination depth to gather more than a couple of reviews when available.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    query = f"{normalized_title} {author or ''} libro".strip()

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        search_resp = await client.get(AMAZON_IT_SEARCH_URL, params={"k": query})
        search_resp.raise_for_status()
        search_html = search_resp.text

        # Find first valid ASIN from search results (skip placeholders).
        asin = None
        for match in re.finditer(r'data-asin="([A-Z0-9]{10})"', search_html):
            candidate = match.group(1)
            if candidate and candidate != "" and candidate != "0000000000":
                asin = candidate
                break
        if not asin:
            return []

        snippets: List[ReviewSample] = []
        seen_snippets = set()

        def _extract_amazon_reviewer(context_html: str) -> str:
            patterns = [
                r'data-hook="review-author"[^>]*>(.*?)</a>',
                r'class="a-profile-name"[^>]*>(.*?)</span>',
            ]
            for pattern in patterns:
                m = re.search(pattern, context_html, re.IGNORECASE | re.DOTALL)
                if not m:
                    continue
                name = _clean_review_text(m.group(1))
                if name:
                    return name
            return "Amazon User"

        def _extract_amazon_rating(context_html: str) -> Optional[float]:
            patterns = [
                r'([0-5](?:[\.,]\d+)?)\s+su\s+5\s+stelle',
                r'([0-5](?:[\.,]\d+)?)\s+out of\s+5\s+stars',
            ]
            for pattern in patterns:
                m = re.search(pattern, context_html, re.IGNORECASE)
                if not m:
                    continue
                try:
                    return float(m.group(1).replace(",", "."))
                except Exception:
                    continue
            return None

        patterns = [
            r'data-hook="review-body"[^>]*>\s*<span[^>]*>(.*?)</span>',
            r'class="a-expander-content reviewText review-text-content a-expander-partial-collapse-content"[^>]*>(.*?)</span>',
            r'data-hook="review-collapsed"[^>]*>(.*?)</span>',
            r'class="review-text"[^>]*>(.*?)</span>',
        ]

        for page_num in range(1, max_pages + 1):
            review_url = f"https://www.amazon.it/product-reviews/{asin}?reviewerType=all_reviews&pageNumber={page_num}"
            reviews_resp = await client.get(review_url)
            reviews_resp.raise_for_status()
            page_html = reviews_resp.text

            for pattern in patterns:
                for match in re.finditer(pattern, page_html, re.DOTALL | re.IGNORECASE):
                    cleaned = _clean_user_review_text(match.group(1))
                    if not cleaned or _looks_promotional(cleaned) or _looks_like_synopsis(cleaned):
                        continue

                    context_start = max(0, match.start() - 1300)
                    context_end = min(len(page_html), match.end() + 350)
                    context_html = page_html[context_start:context_end]
                    reviewer = _extract_amazon_reviewer(context_html)
                    rating = _extract_amazon_rating(context_html)
                    if rating is None:
                        continue

                    normalized = re.sub(r"\s+", " ", cleaned).strip().lower()
                    if normalized in seen_snippets:
                        continue
                    seen_snippets.add(normalized)

                    snippets.append(
                        ReviewSample(
                            reviewer=reviewer,
                            rating=rating,
                            text=cleaned[:4000],
                        )
                    )
                    if len(snippets) >= 5:
                        return snippets[:5]

        return snippets[:5]


async def _fetch_amazon_rating(normalized_title: str, author: Optional[str]) -> Tuple[Optional[float], Optional[int]]:
    """Fetch average star rating and (approximate) count from Amazon search/review page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    query = f"{normalized_title} {author or ''} libro".strip()

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        search_resp = await client.get(AMAZON_IT_SEARCH_URL, params={"k": query})
        search_resp.raise_for_status()
        search_html = search_resp.text

        asin = None
        for match in re.finditer(r'data-asin="([A-Z0-9]{10})"', search_html):
            candidate = match.group(1)
            if candidate and candidate != "" and candidate != "0000000000":
                asin = candidate
                break
        if not asin:
            return None, None
        review_url = f"https://www.amazon.it/product-reviews/{asin}?reviewerType=all_reviews"
        reviews_resp = await client.get(review_url)
        reviews_resp.raise_for_status()
        page = reviews_resp.text

    rating = None
    count = None

    rating_match = re.search(r'([0-5],[0-9]|[0-5]\.[0-9]) su 5 stelle', page)
    if rating_match:
        rating_text = rating_match.group(1).replace(",", ".")
        try:
            rating = float(rating_text)
        except ValueError:
            rating = None

    count_match = re.search(r"([\d\.]+) valutazioni", page)
    if count_match:
        try:
            count = int(count_match.group(1).replace(".", ""))
        except ValueError:
            count = None

    return rating, count


async def _fetch_openlibrary_summary(normalized_title: str, author: Optional[str]) -> Optional[str]:
    params = {
        "title": normalized_title,
        "author": author or "",
        "limit": 1,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(OPENLIBRARY_SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    docs = data.get("docs", [])
    if not docs:
        return None
    first_sentence = docs[0].get("first_sentence")
    if isinstance(first_sentence, str):
        return first_sentence.strip()
    if isinstance(first_sentence, list) and first_sentence:
        return str(first_sentence[0]).strip()
    return None


async def _fetch_openlibrary_metadata(normalized_title: str, author: Optional[str]) -> dict:
    params = {
        "title": normalized_title,
        "author": author or "",
        "limit": 1,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(OPENLIBRARY_SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    docs = data.get("docs", [])
    if not docs:
        return {}
    top = docs[0]
    key_raw = top.get("key")
    return {
        "openlibrary_key": str(key_raw).replace("/works/", "") if key_raw else None,
        "first_publish_year": top.get("first_publish_year"),
        "edition_count": top.get("edition_count"),
        "language": ", ".join(top.get("language", [])[:3]) if isinstance(top.get("language"), list) else None,
    }


def _extract_metadata(item: dict, normalized_title: str) -> dict:
    volume = item.get("volumeInfo", {})
    image_links = volume.get("imageLinks", {})
    identifiers = volume.get("industryIdentifiers", [])
    raw_authors = volume.get("authors", [])
    cleaned_authors: List[str] = []
    for entry in raw_authors:
        author_name = str(entry or "").strip()
        lowered = author_name.lower()
        if not author_name:
            continue
        if "wikipedia" in lowered or lowered.startswith("fonte") or "source" in lowered:
            continue
        cleaned_authors.append(author_name)

    isbn = None
    isbn_10 = None
    for ident in identifiers:
        if ident.get("type") == "ISBN_13":
            isbn = ident.get("identifier")
        if ident.get("type") == "ISBN_10" and not isbn_10:
            isbn_10 = ident.get("identifier")
    if not isbn and identifiers:
        isbn = identifiers[0].get("identifier")

    published = volume.get("publishedDate", "")
    year = None
    if isinstance(published, str) and published[:4].isdigit():
        year = int(published[:4])

    cover = (
        image_links.get("thumbnail")
        or image_links.get("smallThumbnail")
        or image_links.get("medium")
    )

    avg_rating = volume.get("averageRating")
    ratings_count = volume.get("ratingsCount", 0)
    positive_ratio = None
    if isinstance(avg_rating, (int, float)):
        positive_ratio = round(min(max(avg_rating / 5, 0), 1), 3)
        if ratings_count and ratings_count < 10:
            positive_ratio = positive_ratio * 0.7 + 0.3 * 0.7

    return {
        "title": volume.get("title", normalized_title),
        "author": ", ".join(cleaned_authors) or None,
        "subtitle": volume.get("subtitle"),
        "publication_year": year,
        "published_date": volume.get("publishedDate"),
        "pages": volume.get("pageCount"),
        "isbn": isbn,
        "isbn_10": isbn_10,
        "cover_url": cover,
        "publisher": volume.get("publisher"),
        "categories": list(volume.get("categories", [])),
        "language": volume.get("language"),
        "print_type": volume.get("printType"),
        "info_link": volume.get("infoLink"),
        "preview_link": volume.get("previewLink"),
        "canonical_volume_link": volume.get("canonicalVolumeLink"),
        "average_rating": float(avg_rating) if isinstance(avg_rating, (int, float)) else None,
        "description": volume.get("description"),
        "positive_ratio": positive_ratio,
        "ratings_count": ratings_count,
        "snippet": item.get("searchInfo", {}).get("textSnippet"),
    }


def _build_cover_fallback(book: Book) -> str:
    """Try deterministic cover sources before final placeholder.

    Use OpenLibrary with default fallback so a valid image URL is always returned.
    """
    isbn = _normalize_catalog_code(getattr(book, "isbn", None)) or ""
    isbn10 = _normalize_catalog_code(getattr(book, "isbn_10", None)) or ""
    ean = _normalize_catalog_code(getattr(book, "catalog_ean", None)) or ""
    olid = getattr(book, "openlibrary_key", None) or ""

    for code in (isbn, isbn10, ean):
        if code:
            return f"https://covers.openlibrary.org/b/isbn/{code}-L.jpg?default=true"
    if olid:
        return f"https://covers.openlibrary.org/b/olid/{olid}-L.jpg?default=true"

    # Final deterministic placeholder to avoid broken images in UI.
    seed = abs(hash(book.normalized_title or book.raw_title)) % 50
    return f"https://via.placeholder.com/320x480.png?text=No+Cover+{seed}"


def _reviews_from_snippet(snippet: Optional[str]) -> List[ReviewSample]:
    if not snippet:
        return []

    cleaned = _clean_review_text(snippet)
    if not cleaned or _looks_promotional(cleaned):
        return []

    return [
        ReviewSample(
            reviewer="Google Books Snippet",
            rating=4.5,
            text=cleaned,
        )
    ]


def _reviews_from_snippet_with_discarded(snippet: Optional[str]) -> Tuple[List[ReviewSample], List[str]]:
    if not snippet:
        return [], []
    cleaned = _clean_review_text(snippet)
    if not cleaned:
        return [], []
    if _looks_promotional(cleaned):
        return [], [cleaned]
    return _reviews_from_snippet(cleaned), []


def _reviews_from_description(description: Optional[str]) -> List[ReviewSample]:
    if not description:
        return []

    cleaned = _clean_review_text(description)
    if not cleaned:
        return []

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    snippets = sentences[:2] if sentences else [cleaned[:240]]
    filtered = []
    for snippet in snippets:
        normalized = _clean_review_text(snippet)
        if not normalized or _looks_promotional(normalized):
            continue
        filtered.append(normalized[:280])

    return [
        ReviewSample(
            reviewer=f"Editorial Extract {idx + 1}",
            rating=4.0,
            text=snippet,
        )
        for idx, snippet in enumerate(filtered)
    ]


def _reviews_from_description_with_discarded(description: Optional[str]) -> Tuple[List[ReviewSample], List[str]]:
    if not description:
        return [], []
    cleaned = _clean_review_text(description)
    if not cleaned:
        return [], []

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    snippets = sentences[:3] if sentences else [cleaned[:260]]
    kept: List[str] = []
    discarded: List[str] = []
    for snippet in snippets:
        normalized = _clean_review_text(snippet)
        if not normalized:
            continue
        if _looks_promotional(normalized):
            discarded.append(normalized)
            continue
        kept.append(normalized[:280])

    return [
        ReviewSample(
            reviewer=f"Editorial Extract {idx + 1}",
            rating=4.0,
            text=snippet,
        )
        for idx, snippet in enumerate(kept)
    ], discarded


def _clean_review_text(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = html.unescape(str(text))
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _clean_user_review_text(text: Optional[str]) -> str:
    """Clean user reviews preserving paragraph breaks for readability."""
    if not text:
        return ""

    cleaned = html.unescape(str(text))
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</(p|div|li|section)>", "\n\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.split("\n")]
    compact: List[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank:
                compact.append("")
            previous_blank = True
            continue
        compact.append(line)
        previous_blank = False

    return "\n".join(compact).strip()


def _looks_promotional(text: str) -> bool:
    lowered = text.lower()
    promo_markers = [
        "now the acclaimed",
        "hbo series",
        "cultural phenomenon",
        "masterpiece",
        "bestseller",
        "buy now",
        "movie tie-in",
        "new york times",
        "available now",
    ]
    if any(marker in lowered for marker in promo_markers):
        return True

    # Very shouty snippets are often marketing copy.
    alpha_chars = [ch for ch in text if ch.isalpha()]
    if alpha_chars:
        uppercase_ratio = sum(1 for ch in alpha_chars if ch.isupper()) / len(alpha_chars)
        if uppercase_ratio > 0.6:
            return True

    return False


def _looks_like_synopsis(text: str) -> bool:
    lowered = (text or "").lower()

    synopsis_markers = [
        "la storia segue",
        "il romanzo racconta",
        "segue le vicende",
        "in un futuro",
        "dopo millenni",
        "la trama",
        "the story follows",
        "the novel follows",
        "set in",
        "plot",
    ]
    marker_hits = sum(1 for marker in synopsis_markers if marker in lowered)

    opinion_markers = [
        " secondo me ",
        " a mio ",
        " penso ",
        " trovo ",
        " non mi ",
        " mi sembra ",
        " i think ",
        " for me ",
        " i found ",
        " in my opinion ",
    ]
    has_opinion = any(marker in f" {lowered} " for marker in opinion_markers)

    return marker_hits >= 2 and not has_opinion


def _normalize_summary_candidate(text: Optional[str]) -> str:
    cleaned = _clean_review_text(text)
    if not cleaned:
        return ""

    cleaned = cleaned.strip(" -_\t\n")
    lowered = cleaned.lower()
    reject_markers = [
        "google books",
        "informazioni bibliografiche",
        "metadata summary unavailable",
    ]
    if any(marker in lowered for marker in reject_markers):
        return ""
    if len(cleaned) < 90:
        return ""
    return cleaned


def _extract_summary_from_google_books_html(page_html: str) -> Optional[str]:
    if not page_html:
        return None

    patterns = [
        r'<meta\s+property="og:description"\s+content="(.*?)"',
        r'<meta\s+name="description"\s+content="(.*?)"',
        r'itemprop="description"[^>]*>(.*?)</',
        r'class="[^\"]*gb-segment-text[^\"]*"[^>]*>(.*?)</',
    ]

    for pattern in patterns:
        match = re.search(pattern, page_html, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        candidate = _normalize_summary_candidate(match.group(1))
        if candidate:
            return candidate

    # Fallback: scan long paragraph-like chunks from rendered HTML.
    chunks = re.findall(r"<(?:p|div|span)[^>]*>(.*?)</(?:p|div|span)>", page_html, re.IGNORECASE | re.DOTALL)
    for chunk in chunks:
        candidate = _normalize_summary_candidate(chunk)
        if candidate:
            return candidate

    return None


def _extract_page_count_from_google_books_html(page_html: str) -> Optional[int]:
    if not page_html:
        return None

    patterns = [
        r'"numberOfPages"\s*:\s*"?(\d{2,5})"?',
        r"\b(\d{2,5})\s+pagine\b",
        r"\b(\d{2,5})\s+pages\b",
        r"(?i)pagine\s*</[^>]+>\s*<[^>]+>(\d{2,5})<",
        r"(?i)pages\s*</[^>]+>\s*<[^>]+>(\d{2,5})<",
    ]

    for pattern in patterns:
        match = re.search(pattern, page_html, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        try:
            value = int(match.group(1))
        except Exception:
            continue
        if 20 <= value <= 5000:
            return value

    return None


async def _fetch_google_books_page_summary(links: List[Optional[str]]) -> Optional[str]:
    ordered_links: List[str] = []
    seen = set()
    for link in links:
        if not link:
            continue
        clean_link = str(link).strip()
        if not clean_link or clean_link in seen:
            continue
        seen.add(clean_link)
        ordered_links.append(clean_link)

    if not ordered_links:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        for link in ordered_links:
            try:
                resp = await client.get(link)
                resp.raise_for_status()
                extracted = _extract_summary_from_google_books_html(resp.text)
                if extracted:
                    return extracted
            except Exception:
                continue

    return None


async def _fetch_google_books_page_count(links: List[Optional[str]]) -> Optional[int]:
    ordered_links: List[str] = []
    seen = set()
    for link in links:
        if not link:
            continue
        clean_link = str(link).strip()
        if not clean_link or clean_link in seen:
            continue
        seen.add(clean_link)
        ordered_links.append(clean_link)

    if not ordered_links:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        for link in ordered_links:
            try:
                resp = await client.get(link)
                resp.raise_for_status()
                extracted = _extract_page_count_from_google_books_html(resp.text)
                if extracted:
                    return extracted
            except Exception:
                continue

    return None



def _reviews_from_rating_signal(rating: Optional[float], count: int) -> List[ReviewSample]:
    if rating is None and not count:
        return []
    count_text = f" over {count} ratings" if count else ""
    rating_text = f"{rating:.2f}/5" if rating is not None else "N/A"
    return [
        ReviewSample(
            reviewer="Public Rating Signal",
            rating=float(rating or 3.5),
            text=f"Average reader score {rating_text}{count_text}.",
        )
    ]


def _reviews_from_user_snippets(source: str, snippets: List[str], default_rating: float = 4.0) -> List[ReviewSample]:
    output: List[ReviewSample] = []
    seen_texts = set()
    for idx, snippet in enumerate(snippets[:3]):
        cleaned = _clean_user_review_text(snippet)
        if not cleaned or _looks_promotional(cleaned) or _looks_like_synopsis(cleaned):
            continue

        key = re.sub(r"\s+", " ", cleaned).strip().lower()
        if key in seen_texts:
            continue
        seen_texts.add(key)

        output.append(
            ReviewSample(
                reviewer=f"{source} User Review {idx + 1}",
                rating=default_rating,
                text=cleaned[:4000],
            )
        )
    return output


async def enrich_book(book: Book) -> Book:
    """Enrich a book using Google Books plus Goodreads scrape; fallback to safe defaults."""
    try:
        discarded_examples: List[str] = []
        item = await _fetch_google_books(
            book.normalized_title,
            book.author,
            getattr(book, "catalog_publisher", None),
            getattr(book, "catalog_ean", None),
        )
        meta = _extract_metadata(item, book.normalized_title)
        book.isbn = meta.get("isbn")
        book.isbn_10 = meta.get("isbn_10")
        book.published_date = meta.get("published_date")
        book.publication_year = meta.get("publication_year")
        book.pages = meta.get("pages")
        book.cover_url = meta.get("cover_url")
        book.publisher = meta.get("publisher")
        book.categories = meta.get("categories", [])
        book.subtitle = meta.get("subtitle")
        book.language = meta.get("language")
        book.print_type = meta.get("print_type")
        book.info_link = meta.get("info_link")
        book.preview_link = meta.get("preview_link")
        book.canonical_volume_link = meta.get("canonical_volume_link")
        # Rating policy: keep score only from Goodreads; ignore API ratings.
        book.average_rating = None
        book.ratings_count = 0
        if getattr(book, "catalog_ean", None):
            book.author = meta.get("author") or book.author
        else:
            book.author = book.author or meta.get("author")
        canonical_meta_title = normalize_title(meta.get("title"), book.author) if meta.get("title") else ""
        if canonical_meta_title:
            book.raw_title = canonical_meta_title
            book.normalized_title = canonical_meta_title
        book.positive_ratio = None
        # Reviews must come from real user-review sources only (no synthetic editorial snippets).
        book.review_samples = []
        if meta.get("description"):
            book.fetched_summary = str(meta.get("description")).strip()
            book.summary_source = "google_books_api"

        # Prefer richer story summaries from Google Books web pages when available.
        try:
            page_count = await _fetch_google_books_page_count(
                [
                    book.canonical_volume_link,
                    book.info_link,
                    book.preview_link,
                ]
            )
            if page_count:
                book.pages = page_count

            page_summary = await _fetch_google_books_page_summary(
                [
                    book.canonical_volume_link,
                    book.info_link,
                    book.preview_link,
                ]
            )
            if page_summary and (
                not book.fetched_summary
                or len(page_summary) > len((book.fetched_summary or "").strip())
            ):
                book.fetched_summary = page_summary
                book.summary_source = "google_books_page"
        except Exception:
            pass

        # Try Goodreads to refine sentiment.
        try:
            goodreads_book_url = await _find_goodreads_book_url(book.normalized_title, book.author)
            book.goodreads_link = goodreads_book_url

            gr_rating, gr_count, gr_desc = await _fetch_goodreads_rating(
                book.normalized_title,
                book.author,
                book_url=goodreads_book_url,
            )
            if gr_rating:
                gr_ratio = min(max(gr_rating / 5, 0), 1)
                if gr_count and gr_count < 20:
                    gr_ratio = gr_ratio * 0.7 + 0.3 * 0.65
                book.positive_ratio = gr_ratio
                book.average_rating = gr_rating
                if gr_count:
                    book.ratings_count = gr_count
            if gr_desc and not book.fetched_summary:
                book.fetched_summary = str(gr_desc).strip()
                book.summary_source = "goodreads_crawler"
        except Exception:
            pass

        # Fetch user-generated snippets from Goodreads when available.
        try:
            goodreads_reviews = await _fetch_goodreads_user_reviews(
                book.normalized_title,
                book.author,
                book_url=getattr(book, "goodreads_link", None),
            )
            if goodreads_reviews:
                book.review_samples.extend(goodreads_reviews)
        except Exception:
            pass

        # Try Amazon user reviews as additional source (best-effort, paginated for more coverage).
        try:
            amazon_reviews = await _fetch_amazon_user_reviews(book.normalized_title, book.author, max_pages=2)
            if amazon_reviews:
                book.review_samples.extend(amazon_reviews)
        except Exception:
            pass

        try:
            if not book.fetched_summary:
                ol_summary = await _fetch_openlibrary_summary(book.normalized_title, book.author)
                if ol_summary:
                    book.fetched_summary = ol_summary
                    book.summary_source = "openlibrary_crawler"

            ol_meta = await _fetch_openlibrary_metadata(book.normalized_title, book.author)
            if ol_meta:
                if not book.openlibrary_key:
                    book.openlibrary_key = ol_meta.get("openlibrary_key")
                if not book.first_publish_year:
                    book.first_publish_year = ol_meta.get("first_publish_year")
                if not book.edition_count:
                    book.edition_count = ol_meta.get("edition_count")
                if not book.language:
                    book.language = ol_meta.get("language")
                if not book.cover_url:
                    olid = ol_meta.get("openlibrary_key")
                    if olid:
                        book.cover_url = f"https://covers.openlibrary.org/b/olid/{olid}-L.jpg"
        except Exception:
            pass

        # Ensure a cover image is always set (and resolvable).
        if not book.cover_url:
            book.cover_url = _build_cover_fallback(book)

        # Keep only validated real review snippets.
        deduped: List[ReviewSample] = []
        seen = set()
        for sample in book.review_samples:
            sample.text = _clean_user_review_text(sample.text)
            if not sample.text or _looks_promotional(sample.text) or _looks_like_synopsis(sample.text):
                if sample.text:
                    discarded_examples.append(sample.text)
                continue
            key = re.sub(r"\s+", " ", sample.text).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(sample)

        # Keep rating empty when Goodreads has no score.
        if book.average_rating is None:
            book.positive_ratio = None
            book.ratings_count = 0

        book.review_samples = deduped[:5]
        book.discarded_information_examples = [x[:260] for x in discarded_examples if x][:5]

    except Exception:
        book.isbn = book.isbn or f"31213663{_deterministic_int(book, 100, 999)}"
        book.isbn_10 = book.isbn_10 or f"88{_deterministic_int(book, 10000000, 99999999)}"
        book.published_date = book.published_date or str(book.publication_year or 2010)
        book.publication_year = book.publication_year or 2010
        book.pages = book.pages or 355
        book.cover_url = book.cover_url or _build_cover_fallback(book)
        book.publisher = book.publisher or "Unknown Publisher"
        book.categories = book.categories or ["Unknown Genre"]
        book.subtitle = book.subtitle or None
        book.language = book.language or "en"
        book.print_type = book.print_type or "BOOK"
        book.info_link = book.info_link or None
        book.preview_link = book.preview_link or None
        book.canonical_volume_link = book.canonical_volume_link or None
        book.goodreads_link = book.goodreads_link or None
        book.openlibrary_key = book.openlibrary_key or None
        book.first_publish_year = book.first_publish_year or None
        book.edition_count = book.edition_count or None
        book.average_rating = None
        book.ratings_count = 0
        book.positive_ratio = None
        book.review_samples = book.review_samples or []
        book.discarded_information_examples = book.discarded_information_examples or []
        if not book.fetched_summary:
            book.fetched_summary = f"Metadata summary unavailable for {book.normalized_title}."
            book.summary_source = "local_fallback"

    book.status = BookStatus.IN_PROGRESS
    return book
