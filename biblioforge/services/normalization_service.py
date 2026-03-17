import re
from typing import Optional


def normalize_title(raw_title: Optional[str]) -> str:
    """Create a search-friendly title by stripping noise."""
    if not raw_title:
        return ""

    title = raw_title
    title = re.sub(r"\([^)]*\)|\[[^]]*\]", "", title)  # remove bracketed notes
    title = re.sub(r"vol\.?\s*\d+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"edizione\s+limitata", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title)
    title = title.strip(" -_\t\n").strip()
    return title.title()
