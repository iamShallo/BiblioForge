import re
from typing import Optional


def _remove_embedded_author(title: str, author: Optional[str]) -> str:
    if not title or not author:
        return title

    # Remove common separators where the author is appended/prepended to title.
    author_text = re.sub(r"\s+", " ", author).strip(" -_\t\n")
    if not author_text:
        return title

    escaped_author = re.escape(author_text)
    patterns = [
        rf"^\s*{escaped_author}\s*[-|:,]\s*",
        rf"\s*[-|:,]\s*{escaped_author}\s*$",
        rf"^\s*{escaped_author}\s*$",
    ]
    cleaned = title
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" -_\t\n")


def _strip_edition_noise(title: str) -> str:
    if not title:
        return title

    cleaned = title
    edition_patterns = [
        r"\bvol\.?\s*\d+\b",
        r"\bvolume\s*\d+\b",
        r"\bediz\.?\s*(integrale|limitata|deluxe|speciale|illustrata|annotata)?\b",
        r"\bedizione\s+(integrale|limitata|deluxe|speciale|illustrata|annotata)\b",
        r"\b(deluxe|collector'?s|anniversary|special|illustrated|expanded)\s+edition\b",
        r"\b(deluxe|collector'?s|anniversary|special)\b",
    ]
    for pattern in edition_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    return cleaned


def normalize_title(raw_title: Optional[str], author: Optional[str] = None) -> str:
    """Create a search-friendly title by stripping noise."""
    if not raw_title:
        return ""

    title = raw_title
    title = re.sub(r"\([^)]*\)|\[[^]]*\]", "", title)  # remove bracketed notes
    title = _strip_edition_noise(title)
    title = _remove_embedded_author(title, author)
    title = re.sub(r"\s+", " ", title)
    title = title.strip(" -_\t\n").strip()
    return title.title()
