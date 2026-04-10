import re
import unicodedata
from typing import Optional


# Fixe i problemi di encoding del testo (caratteri sporchi, quote strane)
# Fix text encoding issues (weird quotes, mojibake from Latin-1 vs UTF-8)
def _repair_text_noise(text: str) -> str:
    if not text:
        return ""

    # Normalizza il testo Unicode (NFKC = compatibility decomposition)
    cleaned = unicodedata.normalize("NFKC", str(text))
    # Sostituisce i caratteri quotation strani con quote normali
    replacements = {
        "Â«": '"',
        "Â»": '"',
        "«": '"',
        "»": '"',
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "’": "'",
        "‘": "'",
        "‚": "'",
        "‛": "'",
        "`": "'",
        "´": "'",
        "Â": "",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)

    # Separa le parole incollate da errori OCR (es: "COSECaproni" -> "COSE Caproni")
    # Split glued words like "COSECaproni" that often come from OCR/encoding noise.
    cleaned = re.sub(r"\b([A-ZÀ-ÖØ-Ý]{3,})([A-Z][a-zà-öø-ÿ]+)\b", r"\1 \2", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# Rimuove l'autore dal titolo se è stato inserito insieme ("Titolo - Autore")
# Remove author from title if it's been prepended/appended (e.g., "Title - Author")
def _remove_embedded_author(title: str, author: Optional[str]) -> str:
    if not title or not author:
        return title

    # Pulisci il testo dell'autore (rimuove spazi extra)
    # Remove common separators where the author is appended/prepended to title.
    author_text = re.sub(r"\s+", " ", author).strip(" -_\t\n")
    if not author_text:
        return title

    escaped_author = re.escape(author_text)
    author_tokens = [token for token in re.split(r"\s+", author_text) if token]
    flexible_author_pattern = r"[\s\.,]+".join(re.escape(token) for token in author_tokens) if author_tokens else escaped_author

    patterns = [
        rf"^\s*{escaped_author}\s*[-|:,]\s*",
        rf"\s*[-|:,]\s*{escaped_author}\s*$",
        rf"\s*[-|:,]?\s*{flexible_author_pattern}\s*$",
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


# Funzione principale - normalizza il titolo rimuovendo tutti i noise
# Main function - normalize title by removing all noise and irrelevant info
def normalize_title(raw_title: Optional[str], author: Optional[str] = None) -> str:
    if not raw_title:
        return ""

    # Applica le trasformazioni in sequenza
    title = _repair_text_noise(raw_title)  # Fix encoding
    # Rimuovi le virgolette decorative mantenendo il testo interno
    title = title.replace('"', " ")
    # Rimuovi tutto quello che è tra parentesi/quadre (note del catalogo)
    title = re.sub(r"\([^)]*\)|\[[^]]*\]", "", title)  # remove bracketed notes
    title = _strip_edition_noise(title)  # Remove edition info
    # Se l'autore era dentro il titolo, lo rimuove
    title = _remove_embedded_author(title, author)
    # Normalizza gli spazi
    title = re.sub(r"\s+", " ", title)
    title = title.strip(" -_\t\n").strip()
    return title.title()  # Uppercase first letter di ogni parola
