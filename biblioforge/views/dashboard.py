import asyncio
import time
import threading
import base64
import json
import tempfile
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from biblioforge.controllers.pipeline_controller import BookNotFoundError, PipelineController
from biblioforge.models.book import Book, BookStatus, SoldBook
from biblioforge.repositories.sold_book_repository import SoldBookRepository
from biblioforge.services.sheets_sync_service import SheetsSyncService
from biblioforge.services.normalization_service import normalize_title
from biblioforge.services.crawling_service import fetch_ibs_metadata, fetch_preview_by_catalog_code
from biblioforge.views.sales_history import render_sales_history_screen
from biblioforge.utils.batch_update import BatchUpdateManager


controller = PipelineController()
sold_book_repo = SoldBookRepository(
    Path(__file__).parent.parent / "data" / "processed" / "sold_books.json"
)
sheets_sync = SheetsSyncService(
    queue_repository=controller.repository,
    approved_repository=controller.approved_repository,
    state_path=controller.package_root / "data" / "processed" / "sheets_sync_state.json",
)
_sheets_scheduler_lock = threading.Lock()
_sheets_scheduler_started = False
_sheets_sync_pause_event = threading.Event()
_sheets_scheduler_paused_event = threading.Event()
_sheets_sync_operation_lock = threading.Lock()
st.set_page_config(page_title="La Cicogna Triste", layout="wide")
BatchUpdateManager.init_session_state()
st.markdown(
    """
    <style>
    .meta-line {
        font-size: 1.05rem;
        line-height: 1.5;
        margin-bottom: 2px;
    }
    .meta-label {
        font-weight: 700;
    }
    .rejected-item {
        border-left: 3px solid #e0a93b;
        padding-left: 10px;
        margin-bottom: 10px;
    }
    .rejected-example {
        font-size: 0.93rem;
        color: #555;
        margin-top: 4px;
    }
    div[data-testid="stFormSubmitButton"] button[aria-label="+"] {
        color: #1b8f3b;
        border: 1px solid #1b8f3b;
    }
    div[data-testid="stFormSubmitButton"] button[aria-label="-"] {
        color: #c23b22;
        border: 1px solid #c23b22;
    }
    div[data-testid="stFormSubmitButton"] button[aria-label*="+"] {
        color: #1b8f3b !important;
        border: 1px solid #1b8f3b !important;
    }
    div[data-testid="stFormSubmitButton"] button[aria-label*="+"] p {
        color: #1b8f3b !important;
        font-size: 2rem !important;
        font-weight: 900 !important;
        line-height: 1 !important;
    }
    div[data-testid="stFormSubmitButton"] button[aria-label*="-"] {
        color: #c23b22 !important;
        border: 1px solid #c23b22 !important;
    }
    div[data-testid="stFormSubmitButton"] button[aria-label*="-"] p {
        color: #c23b22 !important;
        font-size: 2rem !important;
        font-weight: 900 !important;
        line-height: 1 !important;
    }
    /* Fallback selectors for Streamlit builds where aria-label matching is inconsistent. */
    div[data-testid="stForm"] div[data-testid="stHorizontalBlock"] > div:nth-child(1) div[data-testid="stFormSubmitButton"] button {
        color: #c23b22 !important;
        border: 1px solid #c23b22 !important;
    }
    div[data-testid="stForm"] div[data-testid="stHorizontalBlock"] > div:nth-child(1) div[data-testid="stFormSubmitButton"] button p {
        color: #c23b22 !important;
        font-size: 2rem !important;
        font-weight: 900 !important;
        line-height: 1 !important;
    }
    div[data-testid="stForm"] div[data-testid="stHorizontalBlock"] > div:nth-child(3) div[data-testid="stFormSubmitButton"] button {
        color: #1b8f3b !important;
        border: 1px solid #1b8f3b !important;
    }
    div[data-testid="stForm"] div[data-testid="stHorizontalBlock"] > div:nth-child(3) div[data-testid="stFormSubmitButton"] button p {
        color: #1b8f3b !important;
        font-size: 2rem !important;
        font-weight: 900 !important;
        line-height: 1 !important;
    }
    .floating-download-wrap {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        margin-top: 18px;
        margin-bottom: 12px;
    }
    .floating-download-btn {
        display: inline-block;
        background: #1d4ed8;
        color: #ffffff !important;
        border: 1px solid #1e40af;
        border-radius: 10px;
        padding: 10px 14px;
        font-weight: 700;
        text-decoration: none !important;
        box-shadow: 0 6px 14px rgba(0, 0, 0, 0.25);
    }
    .floating-download-btn:hover {
        background: #1e40af;
        color: #ffffff !important;
    }
    .floating-multi-btn {
        display: inline-block;
        background: #b91c1c;
        color: #ffffff !important;
        border: 1px solid #991b1b;
        border-radius: 10px;
        padding: 10px 14px;
        font-weight: 700;
        text-decoration: none !important;
        box-shadow: 0 6px 14px rgba(0, 0, 0, 0.25);
        cursor: pointer;
    }
    .floating-multi-btn:hover {
        background: #991b1b;
        color: #ffffff !important;
    }
    .floating-sales-btn {
        display: inline-block;
        background: #15803d;
        color: #ffffff !important;
        border: 1px solid #166534;
        border-radius: 10px;
        padding: 10px 14px;
        font-weight: 700;
        text-decoration: none !important;
        box-shadow: 0 6px 14px rgba(0, 0, 0, 0.25);
        cursor: pointer;
    }
    .floating-sales-btn:hover {
        background: #166534;
        color: #ffffff !important;
    }
    .floating-add-btn {
        display: inline-block;
        background: #0f766e;
        color: #ffffff !important;
        border: 1px solid #115e59;
        border-radius: 10px;
        padding: 10px 14px;
        font-weight: 700;
        text-decoration: none !important;
        box-shadow: 0 6px 14px rgba(0, 0, 0, 0.25);
        cursor: pointer;
    }
    .floating-add-btn:hover {
        background: #115e59;
        color: #ffffff !important;
    }
    div[class*="st-key-edit-price-line-"] button {
        background: transparent !important;
        border: 0 !important;
        box-shadow: none !important;
        min-height: 1.2rem !important;
        height: 1.2rem !important;
        padding: 0 !important;
        justify-content: flex-start !important;
    }
    div[class*="st-key-edit-price-line-"] button p {
        font-size: 1.05rem !important;
        margin: 0 !important;
        line-height: 1.5 !important;
        text-align: left !important;
        text-decoration: underline !important;
        text-underline-offset: 3px !important;
        font-weight: 700 !important;
    }
    div[class*="st-key-edit-price-line-"] button:hover p {
        color: #93c5fd !important;
    }
    div[class*="st-key-edit-price-form-"] {
        border: 1px solid #2a3b57;
        border-radius: 14px;
        padding: 14px 14px 10px 14px;
        background: linear-gradient(180deg, rgba(37, 99, 235, 0.12) 0%, rgba(15, 23, 42, 0.42) 100%);
        margin-top: 8px;
    }
    div[class*="st-key-edit-price-form-"] label p {
        font-weight: 700 !important;
        letter-spacing: 0.2px;
    }
    div[class*="st-key-edit-price-form-"] div[data-baseweb="input"] {
        border-radius: 12px !important;
        border: 1px solid #3a4f74 !important;
        background: rgba(8, 14, 28, 0.75) !important;
    }
    div[class*="st-key-edit-price-form-"] div[data-baseweb="input"] input {
        font-size: 1.06rem !important;
        font-weight: 700 !important;
    }
    div[class*="st-key-edit-price-form-"] div[data-testid="stFormSubmitButton"] button {
        min-height: 2.6rem !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        box-shadow: none !important;
    }
    div[class*="st-key-edit-price-form-"] div[data-testid="stHorizontalBlock"] > div:nth-child(1) div[data-testid="stFormSubmitButton"] button {
        background: linear-gradient(90deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: #ffffff !important;
        border: 1px solid #1e40af !important;
    }
    div[class*="st-key-edit-price-form-"] div[data-testid="stHorizontalBlock"] > div:nth-child(1) div[data-testid="stFormSubmitButton"] button p {
        color: #ffffff !important;
        font-size: 1rem !important;
        font-weight: 700 !important;
        line-height: 1.2 !important;
    }
    div[class*="st-key-edit-price-form-"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stFormSubmitButton"] button {
        background: rgba(15, 23, 42, 0.72) !important;
        color: #dbeafe !important;
        border: 1px solid #475569 !important;
    }
    div[class*="st-key-edit-price-form-"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stFormSubmitButton"] button p {
        color: #dbeafe !important;
        font-size: 1rem !important;
        font-weight: 700 !important;
        line-height: 1.2 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def sync_books_file_state() -> None:
    books_path = controller.repository.storage_path
    try:
        current_mtime = books_path.stat().st_mtime
    except FileNotFoundError:
        current_mtime = 0.0

    cached_mtime = st.session_state.get("books_file_mtime")
    if cached_mtime is None:
        st.session_state["books_file_mtime"] = current_mtime
        return

    if current_mtime != cached_mtime:
        st.session_state["books_file_mtime"] = current_mtime
        preserved_selected = (
            st.session_state.get("pending_selected_book_id")
            or st.session_state.get("selected_book_id")
        )
        for key in [
            "auto_metadata_checked_ids",
            "last_manual_insert_message",
            "last_reject_message",
            "last_approve_message",
            "ingest_candidates",
            "ingest_input",
            "manual_ingest_title",
            "manual_ingest_author",
            "manual_ingest_catalog_code",
            "manual_last_autosearch_code",
            "manual_clear_input_next_run",
            "multi_sale_cart",
            "multi_sale_scan_input",
            "multi_sale_last_autosearch_code",
            "multi_sale_clear_input_next_run",
            "last_multi_sale_message",
            "last_multi_sale_feedback",
        ]:
            st.session_state.pop(key, None)
        # Keep the current selection stable across automatic file refreshes.
        if preserved_selected:
            st.session_state["selected_book_id"] = preserved_selected
            st.session_state.pop("pending_selected_book_id", None)
        st.rerun()


def _selection_base_title(book: Book) -> str:
    title = normalize_title(book.raw_title or book.normalized_title, book.author)
    return (title or book.normalized_title or book.raw_title or "Titolo sconosciuto").strip()


def _selection_code(book: Book) -> str:
    """Return the best code shown in selectors (EAN, ISBN, or ISBN-10)."""
    for raw in (
        getattr(book, "catalog_ean", None),
        getattr(book, "isbn", None),
        getattr(book, "isbn_10", None),
    ):
        text = str(raw or "").strip()
        if text:
            return text
    return "-"


def _selection_label(book: Book, duplicate_title_counts: Counter[str]) -> str:
    title = _selection_base_title(book)
    author = (book.author or "Autore sconosciuto").strip()
    code = _selection_code(book)
    code_label = f"EAN/ISBN {code}" if code != "-" else "EAN/ISBN -"

    # Add a tiny id suffix only when multiple entries share the same visible title.
    duplicate_suffix = ""
    if duplicate_title_counts[title.casefold()] > 1:
        duplicate_suffix = f" | ID {book.id[-6:]}"

    return f"{title} - {author} | {code_label}{duplicate_suffix}"


def _book_metadata_score(book: Book) -> int:
    return controller._metadata_score(book)


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip().replace(",", ".")
        if not text:
            return None
        return float(text)
    except (ValueError, TypeError):
        return None


def _safe_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        text = str(value).strip()
        if not text:
            return 0
        return int(float(text))
    except (ValueError, TypeError):
        return 0


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return None


def _optional_float(value: object) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _csv_to_list(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _missing_cover_image_data_uri() -> str:
    """Inline SVG placeholder shown when no valid cover image is available."""
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='480' viewBox='0 0 320 480'>"
        "<rect width='320' height='480' fill='#e5e7eb'/>"
        "<rect x='44' y='60' width='232' height='332' rx='16' fill='#cbd5e1' stroke='#94a3b8' stroke-width='3'/>"
        "<path d='M88 292 L142 236 L184 278 L214 248 L262 300 L262 350 L88 350 Z' fill='#94a3b8'/>"
        "<circle cx='118' cy='152' r='24' fill='#94a3b8'/>"
        "<text x='160' y='418' text-anchor='middle' font-size='24' font-family='Arial, sans-serif' fill='#334155'>"
        "Copertina non disponibile"
        "</text>"
        "</svg>"
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _cover_image_source(book: Book) -> str:
    """Return a reliable image source, falling back to a local placeholder."""
    cover_url = str(getattr(book, "cover_url", "") or "").strip()
    if not cover_url:
        return _missing_cover_image_data_uri()

    if controller._looks_like_placeholder_cover(cover_url):
        return _missing_cover_image_data_uri()

    if not re.match(r"^https?://", cover_url, flags=re.IGNORECASE):
        return _missing_cover_image_data_uri()

    return bust_cache(cover_url, book.id)


def _summary_display_value(summary: str | None) -> str:
    """Hide malformed machine/code blobs and provide a safe readable fallback."""
    text = str(summary or "").strip()
    if not text:
        return "Nessun riassunto disponibile"

    lowered = text.lower()
    code_markers = [
        "function(",
        "=>",
        "typeof",
        "json.parse",
        "return ",
        "var ",
        "const ",
        "let ",
    ]
    marker_hits = sum(1 for marker in code_markers if marker in lowered)
    punctuation_density = sum(text.count(ch) for ch in "{};<>") / max(len(text), 1)
    if marker_hits >= 2 or punctuation_density > 0.06:
        return "Nessun riassunto disponibile"

    return text


def _rank_books_by_metadata(books: list[Book]) -> list[Book]:
    return sorted(
        books,
        key=lambda book: (
            _book_metadata_score(book),
            int(getattr(book, "catalog_quantity", 0) or 0),
            int(getattr(book, "ratings_count", 0) or 0),
            book.id,
        ),
        reverse=True,
    )


def request_selected_book(book_id: str | None) -> None:
    if not book_id:
        return
    st.session_state["pending_selected_book_id"] = book_id
    st.session_state["pending_selected_book_id_trusted"] = True


def apply_pending_selected_book(pending_ids: list[str]) -> None:
    pending_selected = st.session_state.pop("pending_selected_book_id", None)
    trusted_pending = bool(st.session_state.pop("pending_selected_book_id_trusted", False))
    if trusted_pending and pending_selected and pending_selected in pending_ids:
        st.session_state["selected_book_id"] = pending_selected


def mark_book_selection_change() -> None:
    """Flag the currently selected book for immediate metadata refresh."""
    selected = st.session_state.get("selected_book_id")
    if selected:
        st.session_state["force_metadata_refresh_book_id"] = selected


def focus_text_input(label: str) -> None:
    escaped_label = json.dumps(label)
    components.html(
        f"""
        <script>
        (function() {{
            const focusField = () => {{
                const label = {escaped_label};
                const input = window.parent.document.querySelector('input[aria-label="' + label + '"]');
                if (input) {{
                    input.focus();
                    if (typeof input.select === 'function') {{
                        input.select();
                    }}
                }}
            }};
            focusField();
            setTimeout(focusField, 150);
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def set_browser_tab_title(title: str) -> None:
    escaped_title = json.dumps(title)
    components.html(
        f"""
        <script>
        (function() {{
            document.title = {escaped_title};
            if (window.parent && window.parent.document) {{
                window.parent.document.title = {escaped_title};
            }}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def focus_and_autoblur_isbn_input(label: str, should_focus: bool = False) -> None:
    escaped_label = json.dumps(label)
    components.html(
        f"""
        <script>
        (function() {{
            const install = () => {{
                const label = {escaped_label};
                const selector = 'input[aria-label="' + label + '"]';
                const input = window.parent.document.querySelector(selector);
                if (!input) {{
                    return false;
                }}
                if ({'true' if should_focus else 'false'}) {{
                    input.focus();
                    if (typeof input.select === 'function') {{
                        input.select();
                    }}
                }}
                return true;
            }};
            let attempts = 0;
            const keepFocused = setInterval(() => {{
                attempts += 1;
                const found = install();
                if (attempts >= 240 || found) {{
                    clearInterval(keepFocused);
                }}
            }}, 250);
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def ensure_isbn_auto_trigger(label: str) -> None:
    escaped_label = json.dumps(label)
    script = """
        <script>
        (function() {
            const parentWindow = window.parent;
            const label = __LABEL__;
            const selector = 'input[aria-label="' + label + '"]';

            if (!parentWindow.__biblioforgeIsbnWatchers) {
                parentWindow.__biblioforgeIsbnWatchers = {};
            }

            const existing = parentWindow.__biblioforgeIsbnWatchers[label];
            if (existing) {
                clearInterval(existing);
            }

            const triggerIfReady = (input) => {
                if (!input) {
                    return;
                }
                const normalized = (input.value || '').replace(/[^0-9A-Za-z]/g, '');
                const lastSent = input.dataset.biblioforgeLastSubmittedIsbn || '';
                if (normalized.length >= 13) {
                    if (lastSent !== normalized) {
                        input.dataset.biblioforgeLastSubmittedIsbn = normalized;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        setTimeout(() => input.blur(), 120);
                    }
                } else {
                    input.dataset.biblioforgeLastSubmittedIsbn = '';
                }
            };

            const tick = () => {
                const input = parentWindow.document.querySelector(selector);
                if (!input) {
                    return;
                }
                if (input.dataset.biblioforgeIsbnImmediateInstalled !== '1') {
                    input.dataset.biblioforgeIsbnImmediateInstalled = '1';
                    input.addEventListener('input', () => triggerIfReady(input));
                    input.addEventListener('paste', () => {
                        setTimeout(() => triggerIfReady(input), 50);
                        setTimeout(() => triggerIfReady(input), 150);
                    });
                }
                triggerIfReady(input);
            };

            parentWindow.__biblioforgeIsbnWatchers[label] = setInterval(tick, 40);
            tick();
        })();
        </script>
        """.replace("__LABEL__", escaped_label)
    components.html(
        script,
        height=0,
        width=0,
    )


def request_isbn_refocus(scope: str) -> None:
    st.session_state[f"{scope}_isbn_refocus"] = True
    st.session_state[f"{scope}_isbn_refocus_until"] = time.time() + 60


def render_isbn_refocus(scope: str, label: str) -> None:
    refocus_until = float(st.session_state.get(f"{scope}_isbn_refocus_until", 0) or 0)
    if st.session_state.pop(f"{scope}_isbn_refocus", False) or refocus_until >= time.time():
        focus_and_autoblur_isbn_input(label, should_focus=True)
        st.session_state[f"{scope}_isbn_refocus_until"] = max(refocus_until, time.time() + 10)


def render_centered_title_with_logo() -> None:
    """Render centered title with logo image."""
    import os
    from pathlib import Path
    
    # Get the path to the logo
    logo_path = Path(__file__).parent.parent / "imgs" / "Logo_Libreria.png"
    
    # Read and encode the image to base64
    if logo_path.exists():
        with open(logo_path, "rb") as img_file:
            img_data = base64.b64encode(img_file.read()).decode()
        
        st.markdown(
            f"""
            <div style="display: flex; justify-content: center; align-items: center; gap: 20px; margin: 20px 0;">
                <img src="data:image/png;base64,{img_data}" style="width: 250px; height: auto;">
                <h1 style="margin: 0; font-size: 2.5rem;">La Cicogna Triste</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.title("La Cicogna Triste")


def process_pending_approval() -> None:
    """Run a queued approval (set in session) outside the form to avoid double clicks."""
    request = st.session_state.get("approve_request")
    if not request:
        return

    with st.spinner("Salvataggio e approvazione in corso..."):
        approved_book = controller.approve_with_edits(
            request.get("book_id"),
            request.get("summary", ""),
            request.get("tags", []),
        )

    if not approved_book:
        st.session_state["last_approve_message"] = "Impossibile approvare: libro non trovato o gia elaborato."
    else:
        refreshed_pending = controller.list_pending()
        if refreshed_pending:
            request_selected_book(refreshed_pending[0].id)
        else:
            st.session_state.pop("selected_book_id", None)

        st.session_state["last_approve_message"] = "Libro approvato e salvato nel DB finale."

    st.session_state.pop("approve_request", None)
    st.rerun()


def format_duration(seconds: float) -> str:
    seconds = max(seconds, 0)
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def run_sheets_bootstrap_once() -> None:
    """Pull once per browser session to import remote books/sales into local JSON files."""
    if st.session_state.get("sheets_bootstrap_done", False):
        return

    st.session_state["sheets_bootstrap_done"] = True
    cfg = sheets_sync.describe_configuration()
    if not cfg.get("ready", False):
        return

    result = sheets_sync.pull_remote_into_local()
    st.session_state["last_sheets_pull_result"] = {
        "status": result.status,
        "message": result.message,
        "when": time.time(),
    }


def run_scheduled_sheets_push() -> None:
    """Attempt push sync without interrupting user flow."""
    if _sheets_sync_pause_event.is_set():
        return

    if not _sheets_sync_operation_lock.acquire(blocking=False):
        return

    try:
        cfg = sheets_sync.describe_configuration()
        if not cfg.get("ready", False):
            return

        now = time.time()
        push_result = sheets_sync.push_local_to_remote(force=False)
        st.session_state["last_sheets_push_result"] = {
            "status": push_result.status,
            "message": push_result.message,
            "when": now,
        }
    finally:
        _sheets_sync_operation_lock.release()


def push_sheets_after_local_change() -> None:
    """Keep compatibility hook for local edits without forcing an immediate push."""
    st.session_state["sheets_sync_dirty"] = True


def _sheets_scheduler_loop() -> None:
    """Background periodic sync loop that avoids browser reload side effects."""
    while True:
        try:
            if _sheets_sync_pause_event.is_set():
                # Scheduler is paused - signal this state and sleep
                _sheets_scheduler_paused_event.set()
                time.sleep(1)
            else:
                # Not paused - try to acquire lock with timeout and run push
                _sheets_scheduler_paused_event.clear()
                if _sheets_sync_operation_lock.acquire(timeout=2):
                    try:
                        sheets_sync.push_local_to_remote(force=False)
                    finally:
                        _sheets_sync_operation_lock.release()
        except Exception:
            pass
        time.sleep(60)


def pause_sheets_sync() -> None:
    """Pause the background scheduler and wait until it's actually paused."""
    _sheets_sync_pause_event.set()
    # Wait up to 5 seconds for scheduler to actually pause
    _sheets_scheduler_paused_event.wait(timeout=5)


def resume_sheets_sync() -> None:
    _sheets_sync_pause_event.clear()
    _sheets_scheduler_paused_event.clear()


def ensure_sheets_scheduler_running() -> None:
    """Start a single background scheduler for periodic Sheets push."""
    global _sheets_scheduler_started
    with _sheets_scheduler_lock:
        if _sheets_scheduler_started:
            return
        worker = threading.Thread(target=_sheets_scheduler_loop, daemon=True)
        worker.start()
        _sheets_scheduler_started = True


def render_sheets_sync_box() -> None:
    st.markdown("### Sincronizzazione cloud (Google Sheets)")
    cfg = sheets_sync.describe_configuration()
    manual_sheet = st.text_input(
        "Link Google Sheet",
        value=cfg.get("spreadsheet_id", ""),
        key="sheets-manual-id-input",
    )

    resolved_sheet_id = sheets_sync._extract_sheet_id(manual_sheet)
    if resolved_sheet_id:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{resolved_sheet_id}/edit"
        st.markdown(
            f'<a href="{sheet_url}" target="_blank" rel="noopener noreferrer">Apri Google Sheet</a>',
            unsafe_allow_html=True,
        )

    current_cfg = sheets_sync.describe_configuration()
    if current_cfg.get("ready", False):
        st.markdown(
            "<span style='color:#15803d;font-weight:700;'>Sincronizzazione attiva</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<span style='color:#b91c1c;font-weight:700;'>Sincronizzazione non attiva</span>",
            unsafe_allow_html=True,
        )

    remove_col, save_col, update_col = st.columns([2, 2, 2])

    if remove_col.button("Togli database", use_container_width=True, help="Termina sincronizzazione"):
        sheets_sync.disable_connection()
        st.session_state["sheets-manual-id-input"] = ""
        st.warning("Sincronizzazione disattivata.")
        st.rerun()

    if save_col.button("Salva e sincronizza", use_container_width=True):
        _sheets_sync_operation_lock.acquire()
        try:
            linked = sheets_sync.save_connection(manual_sheet, enabled=True)
            if not linked.get("ok"):
                st.error(linked.get("message"))
                return

            with st.spinner("Sincronizzazione in corso..."):
                result = sheets_sync.push_local_to_remote(force=True)
        finally:
            _sheets_sync_operation_lock.release()
        if result.status == "ok":
            st.success("Collegamento salvato. Sincronizzazione iniziale completata con successo.")
            st.rerun()
        elif result.status == "skipped":
            st.info(result.message)
        else:
            st.error(result.message)

    if update_col.button("Update Database", use_container_width=True):
        progress_bar = st.progress(0)
        progress_status = st.empty()

        def _on_pull_progress(progress: int, message: str) -> None:
            progress_bar.progress(max(0, min(100, int(progress))))
            progress_status.caption(message)

        pause_sheets_sync()
        _sheets_sync_operation_lock.acquire()
        try:
            linked = sheets_sync.save_connection(manual_sheet, enabled=True)
            if not linked.get("ok"):
                st.error(linked.get("message"))
                return

            with st.spinner("Aggiornamento database locale in corso..."):
                pull_result = sheets_sync.pull_remote_into_local(progress_callback=_on_pull_progress)
        finally:
            _sheets_sync_operation_lock.release()
            resume_sheets_sync()

        progress_bar.progress(100)
        st.session_state["last_sheets_pull_result"] = {
            "status": pull_result.status,
            "message": pull_result.message,
            "when": time.time(),
            "details": pull_result.details or {},
            "elapsed_seconds": pull_result.elapsed_seconds,
            "average_seconds": pull_result.average_seconds,
        }

        if pull_result.status == "ok":
            st.success("Database locale aggiornato da Google Sheet.")
            st.caption(pull_result.message)
        elif pull_result.status == "skipped":
            st.info(pull_result.message)
        else:
            st.error(pull_result.message)

    pull_info = st.session_state.get("last_sheets_pull_result")
    if isinstance(pull_info, dict) and pull_info.get("status") == "ok":
        details = pull_info.get("details") or {}
        books = details.get("books") or {}
        sales = details.get("sales") or {}

        elapsed = pull_info.get("elapsed_seconds")
        average = pull_info.get("average_seconds")
        if isinstance(elapsed, (int, float)):
            if isinstance(average, (int, float)):
                st.caption(f"Tempo ultimo update: {elapsed:.1f}s | Tempo medio: {average:.1f}s")
            else:
                st.caption(f"Tempo ultimo update: {elapsed:.1f}s")

        with st.expander("Dettaglio modifiche importate (Update Database)", expanded=False):
            st.markdown(
                "\n".join(
                    [
                        f"- Libri aggiunti: {int(books.get('added', 0) or 0)}",
                        f"- Libri rimossi: {int(books.get('deleted', 0) or 0)}",
                        f"- Doppioni rimossi: {int(books.get('duplicates_pruned', 0) or 0)}",
                        f"- Doppioni rimossi su Google Sheet: {int(books.get('remote_duplicates_pruned', 0) or 0)}",
                        f"- Libri modificati: {int(books.get('updated', 0) or 0)}",
                        f"- Vendite aggiunte: {int(sales.get('added', 0) or 0)}",
                        f"- Vendite modificate: {int(sales.get('updated', 0) or 0)}",
                    ]
                )
            )

            added_books = books.get("added_items") or []
            if added_books:
                st.markdown("**Libri aggiunti**")
                for item in added_books:
                    st.write(f"- {item}")

            deleted_books = books.get("deleted_items") or []
            if deleted_books:
                st.markdown("**Libri rimossi**")
                for item in deleted_books:
                    st.write(f"- {item}")

            updated_books = books.get("updated_items") or []
            if updated_books:
                st.markdown("**Libri modificati**")
                for item in updated_books:
                    if isinstance(item, dict):
                        book_label = item.get("book") or "Libro"
                        changed_fields = ", ".join(str(field) for field in (item.get("changed_fields") or []))
                        st.write(f"- {book_label}: {changed_fields}")

            added_sales = sales.get("added_items") or []
            if added_sales:
                st.markdown("**Vendite aggiunte**")
                for item in added_sales:
                    st.write(f"- {item}")

            updated_sales = sales.get("updated_items") or []
            if updated_sales:
                st.markdown("**Vendite modificate**")
                for item in updated_sales:
                    if isinstance(item, dict):
                        sale_label = item.get("sale") or "Vendita"
                        changed_fields = ", ".join(str(field) for field in (item.get("changed_fields") or []))
                        st.write(f"- {sale_label}: {changed_fields}")


def bust_cache(url: str, token: str) -> str:
    if not url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}cb={token}"


def _normalize_source_link(url: str) -> str:
    """Normalize links so equivalent book pages are shown once in UI."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    book_id = (query.get("id") or [""])[0]
    path = parsed.path.rstrip("/")
    if parsed.netloc.endswith("google.com") and book_id:
        return f"google:{book_id}"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def status_label(status: BookStatus) -> str:
    labels = {
        BookStatus.TO_CLEAN: "Da pulire",
        BookStatus.IN_PROGRESS: "In lavorazione",
        BookStatus.TO_APPROVE: "Da approvare",
        BookStatus.APPROVED: "Approvato",
    }
    return labels.get(status, status.value)


def render_context_column(book: Book) -> None:
    st.markdown("### Libro e dati estratti")
    first_publish_year = getattr(book, "first_publish_year", None)
    published_date = getattr(book, "published_date", None)
    isbn_10 = getattr(book, "isbn_10", None)
    edition_count = getattr(book, "edition_count", None)
    language = getattr(book, "language", None)
    print_type = getattr(book, "print_type", None)
    openlibrary_key = getattr(book, "openlibrary_key", None)
    info_link = getattr(book, "info_link", None)
    preview_link = getattr(book, "preview_link", None)
    canonical_volume_link = getattr(book, "canonical_volume_link", None)
    goodreads_link = getattr(book, "goodreads_link", None)
    categories = getattr(book, "categories", [])
    reject_attempts = getattr(book, "reject_attempts", 0)
    catalog_ean = getattr(book, "catalog_ean", None)
    catalog_publisher = getattr(book, "catalog_publisher", None)
    catalog_quantity = getattr(book, "catalog_quantity", None)
    catalog_price = _safe_float(getattr(book, "catalog_price", None))
    edit_manual_state_key = f"show-manual-editor-{book.id}"

    cols = st.columns([1, 2])
    with cols[0]:
        st.image(_cover_image_source(book), width=160)
    with cols[1]:
        st.markdown(f"#### {book.normalized_title or book.raw_title or 'Titolo sconosciuto'}")
        st.caption(book.author or "Autore sconosciuto")

    st.markdown("---")
    metric_items = []
    if catalog_ean:
        metric_items.append(("EAN catalogo", str(catalog_ean)))
    if catalog_publisher:
        metric_items.append(("Editore catalogo", str(catalog_publisher)))
    if catalog_quantity is not None:
        metric_items.append(("Quantita catalogo", str(catalog_quantity)))
    price_text = f"EUR {catalog_price:.2f}" if catalog_price is not None else "N/D"
    metric_items.append(("Prezzo catalogo", price_text))

    if book.publication_year:
        metric_items.append(("Anno edizione", str(book.publication_year)))
    if first_publish_year:
        metric_items.append(("Anno prima pubblicazione", str(first_publish_year)))
    if published_date:
        metric_items.append(("Data pubblicazione", str(published_date)))
    if book.pages:
        metric_items.append(("Pagine", str(book.pages)))
    if book.isbn:
        metric_items.append(("ISBN", str(book.isbn)))
    if isbn_10:
        metric_items.append(("ISBN-10", str(isbn_10)))
    if edition_count:
        metric_items.append(("Numero edizioni", str(edition_count)))
    if book.publisher:
        metric_items.append(("Editore API", book.publisher))
    if language:
        metric_items.append(("Lingua", language))
    if print_type:
        metric_items.append(("Tipo stampa", print_type))
    if openlibrary_key:
        metric_items.append(("Chiave OpenLibrary", openlibrary_key))

    if metric_items:
        st.markdown("#### Metadati")
        left_meta, right_meta = st.columns(2)
        for idx, (label, value) in enumerate(metric_items):
            target = left_meta if idx % 2 == 0 else right_meta
            target.markdown(
                f"<div class='meta-line'><span class='meta-label'>{label}:</span> {value}</div>",
                unsafe_allow_html=True,
            )

    if st.session_state.get(edit_manual_state_key):
        st.markdown("##### Modifica manuale completa")
        with st.form(key=f"edit-manual-form-{book.id}"):
            title_col, author_col = st.columns(2)
            new_title = title_col.text_input("Titolo", value=str(book.normalized_title or book.raw_title or ""))
            new_author = author_col.text_input("Autore", value=str(book.author or ""))

            code_col, isbn10_col = st.columns(2)
            new_catalog_ean = code_col.text_input("EAN catalogo", value=str(getattr(book, "catalog_ean", "") or ""))
            new_isbn10 = isbn10_col.text_input("ISBN-10", value=str(getattr(book, "isbn_10", "") or ""))

            isbn_col, publisher_col = st.columns(2)
            new_isbn = isbn_col.text_input("ISBN", value=str(getattr(book, "isbn", "") or ""))
            new_publisher = publisher_col.text_input("Editore API", value=str(getattr(book, "publisher", "") or ""))

            cat_pub_col, cat_col = st.columns(2)
            new_catalog_publisher = cat_pub_col.text_input("Editore catalogo", value=str(getattr(book, "catalog_publisher", "") or ""))
            new_categories = cat_col.text_input("Categorie (separate da virgola)", value=", ".join(getattr(book, "categories", []) or []))

            qty_col, price_col = st.columns(2)
            new_quantity = qty_col.text_input("Quantita catalogo", value=str(getattr(book, "catalog_quantity", "") or ""))
            new_price = price_col.text_input("Prezzo catalogo (EUR)", value=str(getattr(book, "catalog_price", "") or ""))

            pub_date_col, pub_year_col = st.columns(2)
            new_published_date = pub_date_col.text_input("Data pubblicazione", value=str(getattr(book, "published_date", "") or ""))
            new_publication_year = pub_year_col.text_input("Anno edizione", value=str(getattr(book, "publication_year", "") or ""))

            pages_col, first_year_col = st.columns(2)
            new_pages = pages_col.text_input("Numero pagine", value=str(getattr(book, "pages", "") or ""))
            new_first_publish_year = first_year_col.text_input("Anno prima pubblicazione", value=str(getattr(book, "first_publish_year", "") or ""))

            lang_col, type_col = st.columns(2)
            new_language = lang_col.text_input("Lingua", value=str(getattr(book, "language", "") or ""))
            new_print_type = type_col.text_input("Tipo stampa", value=str(getattr(book, "print_type", "") or ""))

            rating_col, ratings_count_col = st.columns(2)
            new_average_rating = rating_col.text_input("Valutazione media", value=str(getattr(book, "average_rating", "") or ""))
            new_ratings_count = ratings_count_col.text_input("Numero valutazioni", value=str(getattr(book, "ratings_count", "") or ""))

            cover_col, subtitle_col = st.columns(2)
            new_cover_url = cover_col.text_input("URL copertina", value=str(getattr(book, "cover_url", "") or ""))
            new_subtitle = subtitle_col.text_input("Sottotitolo", value=str(getattr(book, "subtitle", "") or ""))

            openlibrary_col, edition_count_col = st.columns(2)
            new_openlibrary_key = openlibrary_col.text_input("Chiave OpenLibrary", value=str(getattr(book, "openlibrary_key", "") or ""))
            new_edition_count = edition_count_col.text_input("Numero edizioni", value=str(getattr(book, "edition_count", "") or ""))

            info_col, preview_col = st.columns(2)
            new_info_link = info_col.text_input("Info link", value=str(getattr(book, "info_link", "") or ""))
            new_preview_link = preview_col.text_input("Preview link", value=str(getattr(book, "preview_link", "") or ""))

            canonical_col, goodreads_col = st.columns(2)
            new_canonical_link = canonical_col.text_input("Canonical volume link", value=str(getattr(book, "canonical_volume_link", "") or ""))
            new_goodreads_link = goodreads_col.text_input("Goodreads link", value=str(getattr(book, "goodreads_link", "") or ""))

            source_col, ratio_col = st.columns(2)
            new_summary_source = source_col.text_input("Summary source", value=str(getattr(book, "summary_source", "") or ""))
            new_positive_ratio = ratio_col.text_input("Positive ratio", value=str(getattr(book, "positive_ratio", "") or ""))

            new_fetched_summary = st.text_area(
                "Fetched summary",
                value=str(getattr(book, "fetched_summary", "") or ""),
                height=120,
            )

            save_col, cancel_col = st.columns(2)
            save_manual = save_col.form_submit_button("Salva modifiche", use_container_width=True)
            cancel_manual = cancel_col.form_submit_button("Annulla", use_container_width=True)

        if cancel_manual:
            st.session_state.pop(edit_manual_state_key, None)
            st.rerun()

        if save_manual:
            latest = controller.repository.get_book(book.id)
            if latest is None:
                st.error("Libro non trovato nel DB.")
            else:
                latest.raw_title = str(new_title or "").strip() or latest.raw_title
                latest.normalized_title = str(new_title or "").strip() or latest.normalized_title
                latest.author = _optional_text(new_author)
                latest.catalog_ean = _optional_text(new_catalog_ean)
                latest.isbn_10 = _optional_text(new_isbn10)
                latest.isbn = _optional_text(new_isbn)
                latest.publisher = _optional_text(new_publisher)
                latest.catalog_publisher = _optional_text(new_catalog_publisher)
                latest.categories = _csv_to_list(new_categories)
                latest.catalog_quantity = _optional_int(new_quantity)
                latest.catalog_price = _optional_float(new_price)
                latest.published_date = _optional_text(new_published_date)
                latest.publication_year = _optional_int(new_publication_year)
                latest.pages = _optional_int(new_pages)
                latest.first_publish_year = _optional_int(new_first_publish_year)
                latest.language = _optional_text(new_language)
                latest.print_type = _optional_text(new_print_type)
                latest.average_rating = _optional_float(new_average_rating)
                latest.ratings_count = _safe_int(new_ratings_count)
                latest.cover_url = _optional_text(new_cover_url)
                latest.subtitle = _optional_text(new_subtitle)
                latest.openlibrary_key = _optional_text(new_openlibrary_key)
                latest.edition_count = _optional_int(new_edition_count)
                latest.info_link = _optional_text(new_info_link)
                latest.preview_link = _optional_text(new_preview_link)
                latest.canonical_volume_link = _optional_text(new_canonical_link)
                latest.goodreads_link = _optional_text(new_goodreads_link)
                latest.summary_source = _optional_text(new_summary_source)
                latest.positive_ratio = _optional_float(new_positive_ratio)
                latest.fetched_summary = _optional_text(new_fetched_summary)

                controller.repository.upsert_book(latest)
                st.success("Metadati libro aggiornati manualmente.")

            st.session_state.pop(edit_manual_state_key, None)
            request_selected_book(book.id)
            st.rerun()

    if categories:
        st.caption(f"Categorie: {', '.join(categories)}")
    source_links = [
        ("Info Google Books", info_link),
        ("Anteprima Google Books", preview_link),
        ("Pagina canonica del volume", canonical_volume_link),
        ("Pagina Goodreads", goodreads_link),
    ]
    seen_links = set()
    for label, link in source_links:
        if not link:
            continue
        normalized = _normalize_source_link(link)
        if normalized in seen_links:
            continue
        seen_links.add(normalized)
        st.markdown(f"[{label}]({link})")
    if reject_attempts:
        st.caption(f"Tentativi di rifiuto: {reject_attempts}")

    rating_value = _safe_float(getattr(book, "average_rating", None))
    if rating_value is not None:
        if rating_value <= 2.0:
            color = "#c23b22"  # red
        elif rating_value <= 4.0:
            color = "#d97706"  # orange
        else:
            color = "#1b8f3b"  # green

        rating_html = f"<span style='color:{color}; font-size:30px; font-weight:800;'>{rating_value:.2f}</span>"
        details = ["Valutazione Goodreads"]
        ratings_count = _safe_int(getattr(book, "ratings_count", 0))
        if ratings_count:
            details.append(f"{ratings_count:,} valutazioni")
        st.markdown(f"{rating_html} &nbsp; {' · '.join(details)}", unsafe_allow_html=True)
    else:
        st.caption("Valutazione Goodreads non disponibile")

    if st.button(
        "Modifica tutti i campi",
        key=f"edit-all-fields-{book.id}",
        use_container_width=True,
    ):
        st.session_state[edit_manual_state_key] = True
        st.rerun()


    # Rejected-information audit remains stored in data, but is intentionally hidden in UI.
def render_editing_column(book: Book) -> None:
    if not book.insights:
        st.warning("Nessun insight AI disponibile per questo libro.")
        return

    with st.form(key=f"editing-form-{book.id}"):
        summary = st.text_area("Riassunto", value=_summary_display_value(book.insights.summary), height=180)
        tags = st.multiselect(
            "Tag",
            options=sorted(
                set(
                    book.insights.tags
                    + book.categories
                    + ["Historical Fiction", "Mystery", "Philosophy", "Theology", "Investigation", "Classic", "Highly Rated"]
                )
            ),
            default=book.insights.tags,
        )
        col_approve, col_reject, col_remove = st.columns([1, 1, 1])
        remove_with_price = col_approve.form_submit_button("-", use_container_width=True)
        reject = col_reject.form_submit_button("Cerca i dati online", use_container_width=True)
        add_quantity = col_remove.form_submit_button("+", use_container_width=True)

        if remove_with_price:
            st.session_state.pop(f"show-quantity-popup-{book.id}", None)
            request_selected_book(book.id)
            st.session_state[f"show-remove-choice-{book.id}"] = True
            st.rerun()
        if reject:
            try:
                with st.spinner("Cerco i dati online..."):
                    updated = controller.reject_and_retry(book.id)
                if updated:
                    request_selected_book(updated.id)
                    checked_ids = set(st.session_state.get("auto_metadata_checked_ids", []))
                    checked_ids.discard(updated.id)
                    st.session_state["auto_metadata_checked_ids"] = list(checked_ids)
                    st.session_state["last_reject_message"] = "Libro rigenerato con una nuova analisi crawl+AI"
                    st.rerun()
                else:
                    st.error("Rifiuto non riuscito: libro selezionato non trovato.")
            except Exception as exc:
                st.error(f"Rifiuto non riuscito: {exc}")

        if add_quantity:
            st.session_state[f"show-quantity-popup-{book.id}"] = True
            st.rerun()

    if st.session_state.get(f"show-remove-choice-{book.id}"):
        st.markdown(
            f"""
            <style>
            div[class*="st-key-remove-choice-form-{book.id}"] div[data-testid="stHorizontalBlock"] > div:nth-child(1) div[data-testid="stFormSubmitButton"] button {{
                background: linear-gradient(90deg, #15803d 0%, #16a34a 100%) !important;
                color: #ffffff !important;
                border: 1px solid #166534 !important;
            }}
            div[class*="st-key-remove-choice-form-{book.id}"] div[data-testid="stHorizontalBlock"] > div:nth-child(1) div[data-testid="stFormSubmitButton"] button p {{
                color: #ffffff !important;
                font-weight: 700 !important;
            }}
            div[class*="st-key-remove-choice-form-{book.id}"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stFormSubmitButton"] button {{
                background: linear-gradient(90deg, #d97706 0%, #f59e0b 100%) !important;
                color: #ffffff !important;
                border: 1px solid #b45309 !important;
            }}
            div[class*="st-key-remove-choice-form-{book.id}"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) div[data-testid="stFormSubmitButton"] button p {{
                color: #ffffff !important;
                font-weight: 700 !important;
            }}
            div[class*="st-key-remove-choice-form-{book.id}"] div[data-testid="stHorizontalBlock"] > div:nth-child(3) div[data-testid="stFormSubmitButton"] button {{
                background: linear-gradient(90deg, #b91c1c 0%, #ef4444 100%) !important;
                color: #ffffff !important;
                border: 1px solid #991b1b !important;
            }}
            div[class*="st-key-remove-choice-form-{book.id}"] div[data-testid="stHorizontalBlock"] > div:nth-child(3) div[data-testid="stFormSubmitButton"] button p {{
                color: #ffffff !important;
                font-weight: 700 !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
        with st.form(key=f"remove-choice-form-{book.id}"):
            st.markdown("### Cosa vuoi fare?")
            st.warning("Scegli se registrare una vendita oppure eliminare il libro dal database. L'eliminazione non registra vendite.")
            sale_col, delete_col, cancel_col = st.columns(3)
            choose_sale = sale_col.form_submit_button("Vendita", use_container_width=True)
            choose_delete = delete_col.form_submit_button("Elimina dal DB", use_container_width=True)
            cancel_remove = cancel_col.form_submit_button("Annulla", use_container_width=True)

        if cancel_remove:
            st.session_state.pop(f"show-remove-choice-{book.id}", None)
            st.rerun()

        if choose_delete:
            latest = controller.repository.get_book(book.id)
            if not latest:
                st.error("Libro non trovato in archivio.")
                st.session_state.pop(f"show-remove-choice-{book.id}", None)
                st.rerun()
            if hasattr(controller, "remove_from_queue"):
                removed = controller.remove_from_queue(book.id)
            elif hasattr(controller.repository, "delete_book"):
                removed = controller.repository.delete_book(book.id)
            else:
                repo = controller.repository
                cache = getattr(repo, "_cache", None)
                persist = getattr(repo, "_persist", None)
                if isinstance(cache, list) and callable(persist):
                    original_len = len(cache)
                    repo._cache = [item for item in cache if getattr(item, "id", None) != book.id]
                    removed = len(repo._cache) != original_len
                    if removed:
                        repo._persist()
                else:
                    removed = False

            if removed:
                st.success("Libro eliminato dal database. Nessuna vendita registrata.")
                st.session_state.pop(f"show-remove-choice-{book.id}", None)
                st.rerun()
            else:
                st.error("Impossibile eliminare il libro selezionato dalla coda.")

        if choose_sale:
            latest = controller.repository.get_book(book.id)
            if not latest:
                st.error("Libro non trovato in archivio.")
                st.session_state.pop(f"show-remove-choice-{book.id}", None)
                st.rerun()

            current_qty = int(getattr(latest, "catalog_quantity", 0) or 0)
            new_qty = current_qty - 1

            if new_qty < 1:
                if hasattr(controller, "remove_from_queue"):
                    removed = controller.remove_from_queue(book.id)
                elif hasattr(controller.repository, "delete_book"):
                    removed = controller.repository.delete_book(book.id)
                else:
                    repo = controller.repository
                    cache = getattr(repo, "_cache", None)
                    persist = getattr(repo, "_persist", None)
                    if isinstance(cache, list) and callable(persist):
                        original_len = len(cache)
                        repo._cache = [item for item in cache if getattr(item, "id", None) != book.id]
                        removed = len(repo._cache) != original_len
                        if removed:
                            repo._persist()
                    else:
                        removed = False

                if removed:
                    sold_book_repo.add_sale(
                        SoldBook(
                            book_id=latest.id,
                            raw_title=latest.raw_title,
                            normalized_title=latest.normalized_title,
                            author=latest.author,
                            price=getattr(latest, "catalog_price", None),
                            quantity=1,
                            sale_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            isbn=latest.isbn,
                            ean=latest.catalog_ean,
                        )
                    )
                    st.success("Quantità arrivata a 0: libro rimosso dal DB e vendita registrata.")
                    st.session_state.pop(f"show-remove-choice-{book.id}", None)
                    st.rerun()
                else:
                    st.error("Impossibile rimuovere il libro selezionato dalla coda.")
            else:
                latest.catalog_quantity = new_qty
                controller.repository.upsert_book(latest)
                sold_book_repo.add_sale(
                    SoldBook(
                        book_id=latest.id,
                        raw_title=latest.raw_title,
                        normalized_title=latest.normalized_title,
                        author=latest.author,
                        price=getattr(latest, "catalog_price", None),
                        quantity=1,
                        sale_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        isbn=latest.isbn,
                        ean=latest.catalog_ean,
                    )
                )
                st.success(f"Quantità ridotta di 1. Quantità totale nel catalogo: {new_qty}. Vendita registrata.")
                st.session_state.pop(f"show-remove-choice-{book.id}", None)
                st.rerun()

    if st.session_state.get(f"show-quantity-popup-{book.id}"):
        with st.form(key=f"add-quantity-form-{book.id}"):
            st.markdown("### Aggiungi quantità al catalogo")
            quantity_to_add = st.number_input(
                "Quante quantità vuoi aggiungere?",
                min_value=1,
                value=1,
                step=1,
            )
            confirm_col, cancel_col = st.columns(2)
            confirm_add = confirm_col.form_submit_button("Conferma", use_container_width=True)
            cancel_add = cancel_col.form_submit_button("Annulla", use_container_width=True)

        if cancel_add:
            st.session_state.pop(f"show-quantity-popup-{book.id}", None)
            st.rerun()

        if confirm_add:
            latest = controller.repository.get_book(book.id)
            if not latest:
                st.error("Libro non trovato in archivio.")
                st.session_state.pop(f"show-quantity-popup-{book.id}", None)
                st.rerun()

            current_qty = int(getattr(latest, "catalog_quantity", 0) or 0)
            new_qty = current_qty + int(quantity_to_add)
            latest.catalog_quantity = new_qty
            controller.repository.upsert_book(latest)
            st.success(f"Aggiunte {int(quantity_to_add)} unità. Quantità totale nel catalogo: {new_qty}.")
            st.session_state.pop(f"show-quantity-popup-{book.id}", None)
            st.rerun()

    catalog_quantity = getattr(book, "catalog_quantity", None)
    qty_value = str(catalog_quantity) if catalog_quantity is not None else "-"
    st.caption(f"Quantità nel catalogo: {qty_value}")


def render_ingestion_box():
    st.markdown("### Aggiungi un libro manualmente")
    st.caption("Oppure scannerizzalo con il codice a barre")
    if "show_isbn_ean_fallback" not in st.session_state:
        st.session_state["show_isbn_ean_fallback"] = False
    if "ingestion_error_message" not in st.session_state:
        st.session_state["ingestion_error_message"] = ""
    if "ingest_candidates" not in st.session_state:
        st.session_state["ingest_candidates"] = []
    if "ingest_input" not in st.session_state:
        st.session_state["ingest_input"] = {}
    if "manual_isbn_refocus" not in st.session_state:
        st.session_state["manual_isbn_refocus"] = True

    if st.session_state.get("ingestion_error_message"):
        st.error(st.session_state["ingestion_error_message"])
        st.session_state["ingestion_error_message"] = ""

    default_title = st.session_state.get("last_failed_title", "")
    default_author = st.session_state.get("last_failed_author", "")
    default_catalog_code = st.session_state.get("last_failed_catalog_code", "")
    def process_manual_ingestion(force: bool = False) -> None:
        title = (st.session_state.get("manual_ingest_title") or "").strip()
        author = (st.session_state.get("manual_ingest_author") or "").strip()
        catalog_code = (st.session_state.get("manual_ingest_catalog_code") or "").strip()
        candidates = []

        if not force and not catalog_code:
            return

        st.session_state["ingestion_error_message"] = ""
        query_title = catalog_code or title
        existing = _find_existing_book_for_manual(query_title, author or None, catalog_code or None)
        st.session_state["show_isbn_ean_fallback"] = False
        resolved_price = None
        resolved_title = query_title
        resolved_author = author or None
        if catalog_code:
            try:
                resolved_meta = asyncio.run(fetch_ibs_metadata(query_title, author or None, catalog_code)) or {}
                resolved_price = resolved_meta.get("price")
                resolved_title = (resolved_meta.get("title") or title or query_title).strip() or query_title
                resolved_author = (resolved_meta.get("authors") or author or "").strip() or None
            except Exception:
                resolved_price = None

        if catalog_code and existing is not None:
            latest = controller.repository.get_book(existing.id)
            if not latest:
                st.error("Libro non trovato nel DB.")
                request_isbn_refocus("manual")
                st.rerun()

            current_qty = int(getattr(latest, "catalog_quantity", 0) or 0)
            latest.catalog_quantity = current_qty + 1
            if resolved_price is not None and getattr(latest, "catalog_price", None) is None:
                latest.catalog_price = resolved_price
            controller.repository.upsert_book(latest)
            price_message = (
                f"EUR {float(getattr(latest, 'catalog_price', 0.0) or 0.0):.2f}"
                if getattr(latest, "catalog_price", None) is not None
                else "non disponibile"
            )
            st.session_state["last_manual_insert_message"] = (
                f"Libro già presente aggiornato: {latest.normalized_title or latest.raw_title} | Quantità aggiornata: {latest.catalog_quantity} | Prezzo IBS: {price_message}"
            )
            st.session_state["ingest_candidates"] = []
            st.session_state["ingest_input"] = {}
            st.session_state["last_failed_title"] = ""
            st.session_state["last_failed_author"] = ""
            st.session_state["last_failed_catalog_code"] = ""
            st.session_state["manual_clear_input_next_run"] = True
            request_selected_book(latest.id)
            request_isbn_refocus("manual")
            st.rerun()

        if catalog_code:
            try:
                book = controller.ingest_raw_book(
                    resolved_title,
                    resolved_author,
                    catalog_ean=catalog_code or None,
                    catalog_price=resolved_price,
                    catalog_quantity=1,
                    allow_low_confidence=True,
                )

                inserted_price = getattr(book, "catalog_price", None)
                price_message = f"EUR {float(inserted_price):.2f}" if inserted_price is not None else "non disponibile"
                st.session_state["last_manual_insert_message"] = (
                    f"Libro inserito con successo: {book.normalized_title} | Prezzo IBS: {price_message}"
                )
                st.session_state["ingest_candidates"] = []
                st.session_state["ingest_input"] = {}
                st.session_state["last_failed_title"] = ""
                st.session_state["last_failed_author"] = ""
                st.session_state["last_failed_catalog_code"] = ""
                st.session_state["manual_clear_input_next_run"] = True
                request_selected_book(book.id)
                request_isbn_refocus("manual")
                st.rerun()
            except BookNotFoundError:
                candidates = controller.find_candidates(
                    query_title,
                    author or None,
                    catalog_publisher=None,
                    catalog_ean=catalog_code or None,
                )
                st.session_state["ingest_candidates"] = candidates
                st.session_state["ingest_input"] = {
                    "title": title,
                    "author": author,
                    "catalog_ean": catalog_code,
                }
                if not candidates:
                    st.session_state["show_isbn_ean_fallback"] = True
                    st.session_state["last_failed_title"] = title
                    st.session_state["last_failed_author"] = author
                    st.session_state["last_failed_catalog_code"] = catalog_code
                    st.session_state["ingestion_error_message"] = (
                        "Nessun candidato trovato. Aggiungi autore o ISBN/EAN per restringere la ricerca."
                    )
                    request_isbn_refocus("manual")
                    st.warning(st.session_state["ingestion_error_message"])
                    return

                st.info("Trovate più corrispondenze. Seleziona il libro corretto qui sotto e conferma.")
        else:
            candidates = controller.find_candidates(
                query_title,
                author or None,
                catalog_publisher=None,
                catalog_ean=None,
            )
            st.session_state["ingest_candidates"] = candidates
            st.session_state["ingest_input"] = {
                "title": title,
                "author": author,
                "catalog_ean": catalog_code,
            }

            if len(candidates) > 1:
                st.info("Trovate più corrispondenze. Seleziona il libro corretto qui sotto e conferma.")
                st.session_state["show_isbn_ean_fallback"] = False
                st.session_state["last_failed_title"] = ""
                st.session_state["last_failed_author"] = ""
                st.session_state["last_failed_catalog_code"] = ""
                return

            selected = candidates[0] if candidates else None
            if selected is not None:
                book = controller.ingest_selected_candidate(
                    selected,
                    fallback_title=title or query_title,
                    fallback_author=author or None,
                    catalog_ean=catalog_code or None,
                    catalog_price=resolved_price,
                    catalog_quantity=1,
                )
            else:
                try:
                    book = controller.ingest_raw_book(
                        query_title,
                        author or None,
                        catalog_ean=catalog_code or None,
                        catalog_price=resolved_price,
                        catalog_quantity=1,
                        allow_low_confidence=True,
                    )
                except BookNotFoundError as exc:
                    st.session_state["show_isbn_ean_fallback"] = True
                    st.session_state["last_failed_title"] = title
                    st.session_state["last_failed_author"] = author
                    st.session_state["last_failed_catalog_code"] = catalog_code
                    st.session_state["ingestion_error_message"] = str(exc)
                    request_isbn_refocus("manual")
                    st.warning(str(exc))
                    return

            inserted_price = getattr(book, "catalog_price", None)
            price_message = f"EUR {float(inserted_price):.2f}" if inserted_price is not None else "non disponibile"
            st.session_state["last_manual_insert_message"] = (
                f"Libro inserito con successo: {book.normalized_title} | Prezzo IBS: {price_message}"
            )
            st.session_state["ingest_candidates"] = []
            st.session_state["ingest_input"] = {}
            st.session_state["last_failed_title"] = ""
            st.session_state["last_failed_author"] = ""
            st.session_state["last_failed_catalog_code"] = ""
            st.session_state["manual_clear_input_next_run"] = True
            request_selected_book(book.id)
            request_isbn_refocus("manual")
            st.rerun()

        if candidates:
            st.session_state["show_isbn_ean_fallback"] = False
        else:
            st.session_state["show_isbn_ean_fallback"] = True
            st.session_state["last_failed_title"] = title
            st.session_state["last_failed_author"] = author
            st.session_state["last_failed_catalog_code"] = catalog_code
            st.session_state["ingestion_error_message"] = (
                "Nessun candidato trovato. Aggiungi autore o ISBN/EAN per restringere la ricerca."
            )
            request_isbn_refocus("manual")
            st.rerun()

    if "manual_ingest_title" not in st.session_state:
        st.session_state["manual_ingest_title"] = default_title
    if "manual_ingest_author" not in st.session_state:
        st.session_state["manual_ingest_author"] = default_author
    if "manual_ingest_catalog_code" not in st.session_state:
        st.session_state["manual_ingest_catalog_code"] = default_catalog_code
    if "manual_last_autosearch_code" not in st.session_state:
        st.session_state["manual_last_autosearch_code"] = ""
    if "manual_clear_input_next_run" not in st.session_state:
        st.session_state["manual_clear_input_next_run"] = False

    if st.session_state.get("manual_clear_input_next_run"):
        st.session_state["manual_ingest_title"] = ""
        st.session_state["manual_ingest_author"] = ""
        st.session_state["manual_ingest_catalog_code"] = ""
        st.session_state["manual_last_autosearch_code"] = ""
        st.session_state["manual_clear_input_next_run"] = False

    title = st.text_input("Titolo", key="manual_ingest_title")
    author = st.text_input("Autore (opzionale)", key="manual_ingest_author")
    catalog_code = st.text_input("ISBN o EAN", key="manual_ingest_catalog_code")

    normalized_catalog_code = _normalize_code(catalog_code)
    if len(normalized_catalog_code) >= 10:
        preview_matches = _find_books_by_isbn(normalized_catalog_code)
        if preview_matches:
            preview = preview_matches[0]
            preview_title = preview.normalized_title or preview.raw_title or "Titolo sconosciuto"
            preview_author = preview.author or "Autore sconosciuto"
            preview_qty = int(getattr(preview, "catalog_quantity", 0) or 0)
            if len(preview_matches) == 1:
                st.caption(
                    f"Trovato subito nel DB: {preview_title} - {preview_author} | Quantità: {preview_qty}"
                )
            else:
                st.caption(
                    f"Trovati {len(preview_matches)} risultati nel DB. Primo: {preview_title} - {preview_author} | Quantità: {preview_qty}"
                )

    ensure_isbn_auto_trigger("ISBN o EAN")
    manual_scan_code = _normalize_code(catalog_code)
    if len(manual_scan_code) >= 13 and manual_scan_code != st.session_state.get("manual_last_autosearch_code", ""):
        st.session_state["manual_clear_input_next_run"] = False
        st.session_state["manual_last_autosearch_code"] = manual_scan_code
        process_manual_ingestion(force=False)
        st.rerun()
    elif len(manual_scan_code) < 13:
        st.session_state["manual_last_autosearch_code"] = ""
    st.caption("Puoi cercare per titolo, per ISBN/EAN, oppure combinando titolo + autore + ISBN/EAN.")

    if st.session_state.get("show_isbn_ean_fallback"):
        st.warning("Libro non trovato. Come ultima risorsa, inserisci ISBN o EAN per risolvere l'edizione esatta.")

    if st.button("Aggiungi al Database"):
        process_manual_ingestion(force=True)

    # Post-form selection step
    candidates = st.session_state.get("ingest_candidates", [])
    ingest_input = st.session_state.get("ingest_input", {})
    if candidates:
        st.markdown("### Seleziona una corrispondenza da importare")
        choice = st.radio(
            "Candidati",
            options=list(range(len(candidates))),
            format_func=lambda idx: (
                f"{candidates[idx].get('title') or 'Titolo sconosciuto'} — "
                f"{candidates[idx].get('authors') or 'Autore sconosciuto'} | "
                f"ISBN/EAN {candidates[idx].get('isbn') or candidates[idx].get('ean') or 'non disponibile'}"
            ),
            key="ingest_choice",
        )
        if st.button("Usa selezione e importa", use_container_width=True):
            selected = candidates[choice] if isinstance(choice, int) and choice < len(candidates) else None
            sel_title = selected.get("title") if selected else ingest_input.get("title")
            sel_author = selected.get("authors") if selected else ingest_input.get("author")
            selection_price = None
            try:
                selection_meta = asyncio.run(
                    fetch_ibs_metadata(
                        sel_title or ingest_input.get("title") or "",
                        sel_author or None,
                        ingest_input.get("catalog_ean") or None,
                    )
                ) or {}
                selection_price = selection_meta.get("price")
            except Exception:
                selection_price = None
            existing = _find_existing_book_for_manual(
                sel_title or ingest_input.get("title"),
                sel_author or None,
                ingest_input.get("catalog_ean") or None,
            )
            if existing is not None:
                latest = controller.repository.get_book(existing.id)
                if latest:
                    current_qty = int(getattr(latest, "catalog_quantity", 0) or 0)
                    latest.catalog_quantity = current_qty + 1
                    if selection_price is not None and getattr(latest, "catalog_price", None) is None:
                        latest.catalog_price = selection_price
                    controller.repository.upsert_book(latest)
                    selection_price_message = (
                        f"EUR {float(getattr(latest, 'catalog_price', 0.0) or 0.0):.2f}"
                        if getattr(latest, "catalog_price", None) is not None
                        else "non disponibile"
                    )
                    st.session_state["last_manual_insert_message"] = (
                        f"Libro già presente aggiornato: {latest.normalized_title or latest.raw_title} | Quantità aggiornata: {latest.catalog_quantity} | Prezzo IBS: {selection_price_message}"
                    )
                    st.session_state["ingest_candidates"] = []
                    st.session_state["ingest_input"] = {}
                    st.session_state["last_failed_title"] = ""
                    st.session_state["last_failed_author"] = ""
                    st.session_state["last_failed_catalog_code"] = ""
                    st.session_state["manual_clear_input_next_run"] = True
                    request_selected_book(latest.id)
                    request_isbn_refocus("manual")
                    st.rerun()

            if selected is not None:
                book = controller.ingest_selected_candidate(
                    selected,
                    fallback_title=ingest_input.get("title"),
                    fallback_author=ingest_input.get("author"),
                    catalog_ean=ingest_input.get("catalog_ean") or None,
                    catalog_price=selection_price,
                    catalog_quantity=1,
                )
            else:
                book = controller.ingest_raw_book(
                    sel_title or ingest_input.get("title") or "",
                    sel_author or None,
                    catalog_ean=ingest_input.get("catalog_ean") or None,
                    catalog_price=selection_price,
                    catalog_quantity=1,
                    allow_low_confidence=True,
                )

            inserted_price = getattr(book, "catalog_price", None)
            price_message = f"EUR {float(inserted_price):.2f}" if inserted_price is not None else "non disponibile"
            st.session_state["last_manual_insert_message"] = (
                f"Libro inserito con successo: {book.normalized_title} | Prezzo IBS: {price_message}"
            )
            st.session_state["ingest_candidates"] = []
            st.session_state["ingest_input"] = {}
            st.session_state["last_failed_title"] = ""
            st.session_state["last_failed_author"] = ""
            st.session_state["last_failed_catalog_code"] = ""
            st.session_state["manual_clear_input_next_run"] = True
            request_selected_book(book.id)
            request_isbn_refocus("manual")
            st.rerun()

    render_isbn_refocus("manual", "ISBN o EAN")


def render_excel_ingestion_box() -> None:
    st.markdown("### Importa da Excel")
    cfg = sheets_sync.describe_configuration()
    if "persisted_skipped_entries" not in st.session_state:
        st.session_state["persisted_skipped_entries"] = []
    if "persisted_skipped_report_path" not in st.session_state:
        st.session_state["persisted_skipped_report_path"] = None
    if "uploaded_excel_temp_path" not in st.session_state:
        st.session_state["uploaded_excel_temp_path"] = None
    if "uploaded_excel_signature" not in st.session_state:
        st.session_state["uploaded_excel_signature"] = None

    uploaded_excel = st.file_uploader(
        "Trascina qui il file Excel oppure selezionalo da Esplora risorse",
        type=["xlsx", "xls"],
        accept_multiple_files=False,
        key="excel-file-uploader",
    )

    if uploaded_excel is not None:
        file_signature = (uploaded_excel.name, getattr(uploaded_excel, "size", None))
        if file_signature != st.session_state.get("uploaded_excel_signature"):
            suffix = Path(uploaded_excel.name).suffix or ".xlsx"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_file.write(uploaded_excel.getbuffer())
                st.session_state["uploaded_excel_temp_path"] = tmp_file.name
                st.session_state["uploaded_excel_signature"] = file_signature

    if st.session_state.get("uploaded_excel_temp_path") and uploaded_excel is not None:
        st.caption(f"File selezionato: {uploaded_excel.name}")

    submitted = st.button("Importa file selezionato", use_container_width=True, disabled=not bool(st.session_state.get("uploaded_excel_temp_path")))

    progress_placeholder = st.empty()
    if submitted:
        start = time.perf_counter()
        progress_bar = progress_placeholder.progress(0, text="Import in corso... 0/0 | mancanti: 0")

        def _on_progress(processed: int, total: int) -> None:
            pct = 0 if total == 0 else int((processed / total) * 100)
            if total > 0 and processed > 0:
                pct = max(1, pct)
            pct = max(0, min(pct, 100))
            remaining = max(0, total - processed)
            text = f"Import in corso... {processed}/{total} | mancanti: {remaining}" if total else "Import in corso... 0/0 | mancanti: 0"
            progress_bar.progress(pct, text=text)

        try:
            import_source = st.session_state.get("uploaded_excel_temp_path")
            if not import_source:
                raise FileNotFoundError("Nessun file Excel selezionato.")

            pause_sheets_sync()
            _sheets_sync_operation_lock.acquire()
            try:
                linked = sheets_sync.save_connection(cfg.get("spreadsheet_id", ""), enabled=True)
                if not linked.get("ok"):
                    raise RuntimeError(linked.get("message"))

                total = controller.ingest_books_from_excel(import_source, progress_callback=_on_progress)
            finally:
                _sheets_sync_operation_lock.release()
                resume_sheets_sync()

            progress_bar.progress(100, text="Import completato")
            sales_total = int(getattr(controller, "last_import_sales_added", 0) or 0)
            st.success(
                f"Importati {total} libri nella coda di revisione e {sales_total} vendite in archivio."
            )
            if getattr(controller, "last_import_skipped", 0):
                skipped_count = controller.last_import_skipped
                st.warning(
                    f"Saltate {skipped_count} righe perche il libro non e stato risolto con sufficiente confidenza."
                )
            st.session_state["persisted_skipped_entries"] = list(
                getattr(controller, "last_import_skipped_details", []) or []
            )
            st.session_state["persisted_skipped_report_path"] = getattr(
                controller,
                "last_import_skipped_report_path",
                None,
            )
            st.session_state["uploaded_excel_signature"] = None
            st.session_state["uploaded_excel_temp_path"] = None

            st.caption(f"Import completato in {format_duration(time.perf_counter() - start)}")
        except Exception as exc:
            progress_bar.progress(0.0, text="Import fallito")
            st.error(f"Import da Excel fallito: {exc}")

    render_sheets_sync_box()

    skipped_details = st.session_state.get("persisted_skipped_entries", [])
    skipped_report_path = st.session_state.get("persisted_skipped_report_path")

    if skipped_details:
        top_left, top_mid, top_right = st.columns([3, 2, 1])
        top_left.warning(
            f"Elementi saltati persistenti: {len(skipped_details)} righe non risolte automaticamente."
        )
        retry_clicked = top_mid.button("Riprova tutti i saltati", use_container_width=True)
        if top_right.button("Svuota lista saltati", use_container_width=True):
            st.session_state["persisted_skipped_entries"] = []
            st.session_state["persisted_skipped_report_path"] = None
            st.rerun()

        if retry_clicked:
            progress = st.progress(0, text="Riprova saltati in corso...")
            def _on_retry_progress(processed: int, total: int) -> None:
                pct = 0 if total == 0 else int((processed / total) * 100)
                pct = max(0, min(pct, 100))
                text = f"Riprova saltati... {processed}/{total}" if total else "Riprova saltati in corso..."
                progress.progress(pct, text=text)

            resolved, still_skipped = controller.retry_skipped_entries(
                skipped_details,
                progress_callback=_on_retry_progress,
            )

            progress.progress(100, text="Riprova saltati completata")
            st.session_state["persisted_skipped_entries"] = still_skipped
            if resolved:
                st.success(f"Riprova completata: risolti {resolved} elementi.")
            if still_skipped:
                st.warning(f"Ancora non risolti: {len(still_skipped)} elementi.")
            st.rerun()

        skipped_df = _skipped_entries_to_dataframe(skipped_details)
        skipped_excel = _to_excel_bytes(skipped_df, "skipped")
        st.download_button(
            label="Scarica lista saltati (Excel)",
            data=skipped_excel,
            file_name="biblioforge_skipped_list.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        with st.expander(f"Vedi elementi saltati ({len(skipped_details)} elementi)", expanded=True):
            st.subheader("Libri saltati")
            for idx, entry in enumerate(skipped_details, 1):
                entry_title = (entry.get("title") or "").strip()
                entry_author = (entry.get("author") or "").strip()
                entry_ean = str(entry.get("ean") or "").strip()

                st.caption(f"{idx}. **{entry.get('title', 'Sconosciuto')}**")
                st.caption(f"Autore: {entry_author or 'Autore sconosciuto'}")
                if entry_ean:
                    st.caption(f"EAN: {entry_ean}")
                reason = entry.get("reason", "Motivo sconosciuto")
                st.caption(f"Motivo: {reason}")

                st.divider()

    if skipped_report_path:
        try:
            import os

            if os.path.exists(skipped_report_path):
                with open(skipped_report_path, "r", encoding="utf-8") as f:
                    report_content = f.read()
                st.download_button(
                    label="Scarica report saltati (JSON)",
                    data=report_content,
                    file_name=os.path.basename(skipped_report_path),
                    mime="application/json",
                )
        except Exception as e:
            st.warning(f"Impossibile caricare il file di report: {e}")


def _to_excel_bytes(dataframe: pd.DataFrame, sheet_name: str) -> bytes:
    excluded_columns = {
        "id",
        "raw_title",
        "isbn_10",
        "publisher",
        "catalog_publisher",
        "catalog_ean",
        "ratings_count",
        "status",
    }
    export_df = dataframe.drop(columns=[c for c in excluded_columns if c in dataframe.columns])
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)
    return output.getvalue()


def _skipped_entries_to_dataframe(skipped_entries: list[dict]) -> pd.DataFrame:
    rows = []
    for entry in skipped_entries:
        rows.append(
            {
                "index": entry.get("index"),
                "title": entry.get("title"),
                "author": entry.get("author"),
                "ean": entry.get("ean"),
                "publisher": entry.get("publisher"),
                "reason": entry.get("reason"),
            }
        )
    return pd.DataFrame(rows)


def _approved_books_to_dataframe(approved_books: list[Book]) -> pd.DataFrame:
    def _best_identifier(book: Book) -> str | None:
        for value in (
            getattr(book, "isbn", None),
            getattr(book, "isbn_10", None),
            getattr(book, "catalog_ean", None),
        ):
            text = str(value or "").strip()
            if text:
                return text
        return None

    rows = []
    for book in approved_books:
        categories = ", ".join(getattr(book, "categories", []) or [])
        rows.append(
            {
                "Titolo": book.normalized_title or book.raw_title,
                "Autore": book.author,
                "Immagine principale": getattr(book, "cover_url", None),
                "Prezzo": getattr(book, "catalog_price", None),
                "ISBN": _best_identifier(book),
                "Data pubblicazione": getattr(book, "published_date", None),
                "Numero pagine": getattr(book, "pages", None),
                "Categoria": categories,
                "Quantita catalogo": getattr(book, "catalog_quantity", None),
                "Valutazione media": getattr(book, "average_rating", None),
            }
        )
    return pd.DataFrame(rows)


def _normalize_code(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def _isbn10_to_isbn13(isbn10: str) -> str:
    core = _normalize_code(isbn10)
    if len(core) != 10:
        return ""
    if not core[:9].isdigit():
        return ""
    if not (core[-1].isdigit() or core[-1] == "X"):
        return ""

    body = f"978{core[:9]}"
    total = 0
    for index, char in enumerate(body):
        total += int(char) * (1 if index % 2 == 0 else 3)
    check = (10 - (total % 10)) % 10
    return f"{body}{check}"


def _isbn13_to_isbn10(isbn13: str) -> str:
    core = _normalize_code(isbn13)
    if len(core) != 13 or not core.startswith("978") or not core.isdigit():
        return ""

    body = core[3:-1]
    total = 0
    for index, char in enumerate(body, start=1):
        total += index * int(char)
    remainder = total % 11
    check = "X" if remainder == 10 else str(remainder)
    return f"{body}{check}"


def _isbn_code_matches(left: str | None, right: str | None) -> bool:
    left_norm = _normalize_code(left)
    right_norm = _normalize_code(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True

    pairs = {
        (_isbn10_to_isbn13(left_norm), right_norm),
        (_isbn10_to_isbn13(right_norm), left_norm),
        (_isbn13_to_isbn10(left_norm), right_norm),
        (_isbn13_to_isbn10(right_norm), left_norm),
    }
    return any(expected and expected == actual for expected, actual in pairs)


def _find_book_by_isbn(code: str) -> Book | None:
    needle = _normalize_code(code)
    if not needle:
        return None

    candidates = _rank_books_by_metadata(controller.repository.list_books())

    for candidate in candidates:
        values = [
            getattr(candidate, "isbn", None),
            getattr(candidate, "isbn_10", None),
            getattr(candidate, "catalog_ean", None),
        ]
        if any(_isbn_code_matches(needle, v) for v in values if v):
            return candidate
    return None


def _find_books_by_isbn(code: str) -> list[Book]:
    needle = _normalize_code(code)
    if not needle:
        return []

    matches: list[Book] = []
    for candidate in controller.repository.list_books():
        values = [
            getattr(candidate, "isbn", None),
            getattr(candidate, "isbn_10", None),
            getattr(candidate, "catalog_ean", None),
        ]
        if any(_isbn_code_matches(needle, v) for v in values if v):
            matches.append(candidate)
    return _rank_books_by_metadata(matches)


def _find_existing_book_for_manual(title: str | None, author: str | None, catalog_ean: str | None) -> Book | None:
    code_matches = _find_books_by_isbn(catalog_ean or "")
    if code_matches:
        canonical_title = normalize_title((title or "").strip(), (author or "").strip() or None)
        author_norm = (author or "").strip().casefold()
        ranked_matches = []
        for candidate in code_matches:
            cand_title = normalize_title(
                (candidate.raw_title or candidate.normalized_title or "").strip(),
                (candidate.author or "").strip() or None,
            )
            cand_author = (candidate.author or "").strip().casefold()
            score = _book_metadata_score(candidate)
            if canonical_title and cand_title == canonical_title:
                score += 2
            if author_norm and cand_author and author_norm == cand_author:
                score += 1
            ranked_matches.append((score, int(getattr(candidate, "catalog_quantity", 0) or 0), candidate.id, candidate))

        ranked_matches.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return ranked_matches[0][3]

    canonical_title = normalize_title((title or "").strip(), (author or "").strip() or None)
    if not canonical_title:
        return None

    author_norm = (author or "").strip().casefold()
    for candidate in controller.repository.list_books():
        cand_title = normalize_title(
            (candidate.raw_title or candidate.normalized_title or "").strip(),
            (candidate.author or "").strip() or None,
        )
        if cand_title != canonical_title:
            continue
        cand_author = (candidate.author or "").strip().casefold()
        if author_norm and cand_author and author_norm != cand_author:
            continue
        return candidate

    return None


def render_multi_sale_screen() -> None:
    set_browser_tab_title("Vendite multiple")
    st.markdown("## Vendite multiple")
    st.caption("Inserisci/scansiona ISBN per aggiungere libri alla vendita.")

    if st.session_state.get("last_multi_sale_message"):
        st.success(st.session_state["last_multi_sale_message"])
        st.session_state["last_multi_sale_message"] = ""

    if "multi_sale_cart" not in st.session_state:
        st.session_state["multi_sale_cart"] = {}

    def process_scanned_isbn() -> bool:
        scanned_isbn = (st.session_state.get("multi_sale_scan_input") or "").strip()
        if not scanned_isbn:
            return False

        found = _find_book_by_isbn(scanned_isbn)
        if not found:
            st.session_state["last_multi_sale_feedback"] = ("error", "ISBN non trovato nel DB.")
            st.session_state["multi_sale_clear_input_next_run"] = True
            request_isbn_refocus("multi_sale")
            return True

        cart = dict(st.session_state.get("multi_sale_cart", {}))
        same_code_books = _find_books_by_isbn(scanned_isbn)
        current_in_catalog = sum(int(getattr(book, "catalog_quantity", 0) or 0) for book in same_code_books)
        current_in_cart = int(cart.get(found.id, 0) or 0)
        proposed_qty = current_in_cart + 1

        if proposed_qty > current_in_catalog:
            st.session_state["last_multi_sale_feedback"] = ("error", "Quantità richiesta non presente nel catalogo.")
            request_isbn_refocus("multi_sale")
        else:
            cart[found.id] = proposed_qty
            st.session_state["multi_sale_cart"] = cart
            st.session_state["last_multi_sale_feedback"] = (
                "success",
                f"Aggiunto: {found.normalized_title or found.raw_title}",
            )

        st.session_state["multi_sale_clear_input_next_run"] = True
        request_isbn_refocus("multi_sale")
        return True

    if "multi_sale_scan_input" not in st.session_state:
        st.session_state["multi_sale_scan_input"] = ""
    if "multi_sale_isbn_refocus" not in st.session_state:
        st.session_state["multi_sale_isbn_refocus"] = True
    if "multi_sale_last_autosearch_code" not in st.session_state:
        st.session_state["multi_sale_last_autosearch_code"] = ""
    if "multi_sale_clear_input_next_run" not in st.session_state:
        st.session_state["multi_sale_clear_input_next_run"] = False

    def handle_multi_sale_scan_change() -> None:
        scanned_code = _normalize_code(st.session_state.get("multi_sale_scan_input"))
        if scanned_code:
            st.session_state["multi_sale_last_autosearch_code"] = scanned_code
        process_scanned_isbn()

    if st.session_state.get("multi_sale_clear_input_next_run"):
        st.session_state["multi_sale_scan_input"] = ""
        st.session_state["multi_sale_last_autosearch_code"] = ""
        st.session_state["multi_sale_clear_input_next_run"] = False

    feedback = st.session_state.pop("last_multi_sale_feedback", None)
    if feedback:
        level, message = feedback
        if level == "error":
            st.error(message)
        else:
            st.success(message)

    isbn_col, add_col = st.columns([4, 1], vertical_alignment="bottom")
    isbn_col.text_input(
        "ISBN (scanner codice a barre)",
        key="multi_sale_scan_input",
        on_change=handle_multi_sale_scan_change,
    )
    ensure_isbn_auto_trigger("ISBN (scanner codice a barre)")
    if add_col.button("Aggiungi", use_container_width=True):
        if process_scanned_isbn():
            st.rerun()

    cart = dict(st.session_state.get("multi_sale_cart", {}))
    if cart:
        st.markdown("### Elenco vendita")
        total = 0.0

        for book_id, qty in list(cart.items()):
            book = controller.repository.get_book(book_id)
            if not book:
                cart.pop(book_id, None)
                continue

            unit_price = float(getattr(book, "catalog_price", 0.0) or 0.0)
            line_total = unit_price * int(qty)
            total += line_total

            img_col, line_col, qty_col, del_col = st.columns([1, 5, 2, 1])
            with img_col:
                st.image(_cover_image_source(book), width=54)
            line_col.markdown(f"**{book.normalized_title or book.raw_title}**")
            line_col.caption(book.author or "Autore sconosciuto")
            qty_col.caption(f"Qta {int(qty)} | EUR {unit_price:.2f}")
            if del_col.button("X", key=f"multi-sale-delete-{book_id}"):
                cart.pop(book_id, None)
                st.session_state["multi_sale_cart"] = cart
                st.rerun()

        st.session_state["multi_sale_cart"] = cart
        st.markdown(f"### Totale vendita: EUR {total:.2f}")

        confirm_col, clear_col = st.columns(2)
        confirm_sale = confirm_col.button("Conferma", use_container_width=True)
        clear_sale = clear_col.button("Svuota", use_container_width=True)

        if clear_sale:
            st.session_state["multi_sale_cart"] = {}
            st.rerun()

        if confirm_sale:
            invalid_items = []
            for book_id, qty in cart.items():
                latest = controller.repository.get_book(book_id)
                if not latest:
                    continue
                code = getattr(latest, "isbn", None) or getattr(latest, "isbn_10", None) or getattr(latest, "catalog_ean", None)
                matched_books = _find_books_by_isbn(str(code or "")) if code else [latest]
                available_qty = sum(int(getattr(book, "catalog_quantity", 0) or 0) for book in matched_books)
                if int(qty) > available_qty:
                    invalid_items.append(latest.normalized_title or latest.raw_title)

            if invalid_items:
                st.error("Quantità richiesta non presente nel catalogo.")
                return

            for book_id, qty in cart.items():
                latest = controller.repository.get_book(book_id)
                if not latest:
                    continue
                code = getattr(latest, "isbn", None) or getattr(latest, "isbn_10", None) or getattr(latest, "catalog_ean", None)
                matched_books = _find_books_by_isbn(str(code or "")) if code else [latest]
                matched_books = sorted(matched_books, key=lambda b: (int(getattr(b, "catalog_quantity", 0) or 0), b.id), reverse=True)
                remaining = int(qty)
                processed_ids: set[str] = set()

                sold_book_repo.add_sale(
                    SoldBook(
                        book_id=latest.id,
                        raw_title=latest.raw_title,
                        normalized_title=latest.normalized_title,
                        author=latest.author,
                        price=getattr(latest, "catalog_price", None),
                        quantity=int(qty),
                        sale_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        isbn=latest.isbn,
                        ean=latest.catalog_ean,
                    )
                )

                for candidate in matched_books:
                    candidate_qty = int(getattr(candidate, "catalog_quantity", 0) or 0)
                    if candidate_qty <= 0:
                        continue

                    if remaining <= 0:
                        if int(qty) == 1 and candidate.id not in processed_ids and candidate_qty <= 1:
                            controller.repository.delete_book(candidate.id)
                            processed_ids.add(candidate.id)
                        continue

                    to_remove = min(candidate_qty, remaining)
                    new_qty = candidate_qty - to_remove
                    if new_qty < 1:
                        controller.repository.delete_book(candidate.id)
                    else:
                        candidate.catalog_quantity = new_qty
                        controller.repository.upsert_book(candidate)
                    processed_ids.add(candidate.id)
                    remaining -= to_remove

                if int(qty) == 1:
                    for candidate in matched_books:
                        if candidate.id in processed_ids:
                            continue
                        candidate_qty = int(getattr(candidate, "catalog_quantity", 0) or 0)
                        if candidate_qty <= 1:
                            controller.repository.delete_book(candidate.id)
            st.session_state["multi_sale_cart"] = {}
            st.session_state["last_multi_sale_message"] = "Vendita multipla registrata."
            st.rerun()

    render_isbn_refocus("multi_sale", "ISBN (scanner codice a barre)")

    st.markdown('<a href="?view=dashboard" target="_blank" rel="noopener noreferrer">Torna alla dashboard</a>', unsafe_allow_html=True)


def render_multi_add_screen() -> None:
    set_browser_tab_title("Aggiunta multipla")
    st.markdown("## Aggiunta multipla libri")
    st.caption("Scannerizza ISBN/EAN: in lista mostriamo solo copertina, titolo e autore. I dati mancanti vengono completati quando premi 'Aggiungi i libri'.")

    if st.session_state.get("last_multi_add_message"):
        st.success(st.session_state["last_multi_add_message"])
        st.session_state["last_multi_add_message"] = ""

    if "multi_add_cart" not in st.session_state:
        st.session_state["multi_add_cart"] = {}
    if "multi_add_scan_input" not in st.session_state:
        st.session_state["multi_add_scan_input"] = ""
    if "multi_add_last_autosearch_code" not in st.session_state:
        st.session_state["multi_add_last_autosearch_code"] = ""
    if "multi_add_clear_input_next_run" not in st.session_state:
        st.session_state["multi_add_clear_input_next_run"] = False
    if "multi_add_isbn_refocus" not in st.session_state:
        st.session_state["multi_add_isbn_refocus"] = True

    def process_scanned_code() -> bool:
        scanned_value = (st.session_state.get("multi_add_scan_input") or "").strip()
        normalized_code = _normalize_code(scanned_value)
        if not normalized_code:
            return False

        cart = dict(st.session_state.get("multi_add_cart", {}))
        existing = _find_book_by_isbn(normalized_code)
        if existing:
            entry_key = f"existing:{existing.id}"
            entry = dict(cart.get(entry_key, {}))
            entry["mode"] = "existing"
            entry["book_id"] = existing.id
            entry["book"] = existing
            entry["code"] = normalized_code
            entry["quantity"] = int(entry.get("quantity", 0) or 0) + 1
            cart[entry_key] = entry
            st.session_state["multi_add_cart"] = cart
            st.session_state["last_multi_add_feedback"] = (
                "success",
                f"Aggiunto in lista: {existing.normalized_title or existing.raw_title}",
            )
        else:
            try:
                exact_preview = {}
                with st.spinner("Recupero dati online..."):
                    try:
                        exact_preview = asyncio.run(fetch_preview_by_catalog_code(normalized_code)) or {}
                    except Exception:
                        exact_preview = {}

                    candidates = []
                    if not exact_preview:
                        candidates = controller.find_candidates(
                            normalized_code,
                            None,
                            catalog_publisher=None,
                            catalog_ean=normalized_code,
                            limit=1,
                        )
                selected = candidates[0] if candidates else None
                ibs_meta = {}
                if not selected and not exact_preview:
                    # Fallback morbido: con alcuni ISBN validi la ricerca candidati e troppo rigida.
                    try:
                        with st.spinner("Recupero dati IBS..."):
                            ibs_meta = asyncio.run(fetch_ibs_metadata(normalized_code, None, normalized_code)) or {}
                    except Exception:
                        ibs_meta = {}

                preview_title = (
                    exact_preview.get("title")
                    or (selected.get("title") if selected else None)
                    or ibs_meta.get("title")
                    or normalized_code
                )
                preview_title = str(preview_title).strip() or normalized_code
                preview_author = (
                    exact_preview.get("authors")
                    or (selected.get("authors") if selected else None)
                    or ibs_meta.get("authors")
                    or ""
                )
                preview_author = str(preview_author).strip() or None
                preview_cover = (
                    exact_preview.get("cover_url")
                    or (selected.get("cover_url") if selected else None)
                    or ibs_meta.get("cover_url")
                    or f"https://covers.openlibrary.org/b/isbn/{normalized_code}-L.jpg?default=true"
                )
                preview_canonical_title = normalize_title(preview_title, preview_author) or preview_title
                preview_book = Book(
                    raw_title=preview_canonical_title,
                    normalized_title=preview_canonical_title,
                    author=preview_author,
                    cover_url=str(preview_cover).strip() or None,
                    catalog_ean=normalized_code,
                    status=BookStatus.IN_PROGRESS,
                )
                entry_key = f"new:{normalized_code}"
                entry = dict(cart.get(entry_key, {}))
                entry["mode"] = "new"
                entry["book"] = preview_book
                entry["candidate"] = selected or None
                entry["code"] = normalized_code
                entry["quantity"] = int(entry.get("quantity", 0) or 0) + 1
                cart[entry_key] = entry
                st.session_state["multi_add_cart"] = cart
                st.session_state["last_multi_add_feedback"] = (
                    "success",
                    f"Preparato: {preview_book.normalized_title or preview_book.raw_title}",
                )
            except Exception as exc:
                st.session_state["last_multi_add_feedback"] = (
                    "error",
                    f"Nessun libro valido trovato per codice {normalized_code}: {exc}",
                )

        st.session_state["multi_add_clear_input_next_run"] = True
        request_isbn_refocus("multi_add")
        return True

    def handle_multi_add_scan_change() -> None:
        scanned_code = _normalize_code(st.session_state.get("multi_add_scan_input"))
        if scanned_code:
            st.session_state["multi_add_last_autosearch_code"] = scanned_code
        process_scanned_code()

    if st.session_state.get("multi_add_clear_input_next_run"):
        st.session_state["multi_add_scan_input"] = ""
        st.session_state["multi_add_last_autosearch_code"] = ""
        st.session_state["multi_add_clear_input_next_run"] = False

    feedback = st.session_state.pop("last_multi_add_feedback", None)
    if feedback:
        level, message = feedback
        if level == "error":
            st.error(message)
        else:
            st.success(message)

    isbn_col, add_col = st.columns([4, 1], vertical_alignment="bottom")
    isbn_col.text_input(
        "ISBN/EAN (scanner codice a barre)",
        key="multi_add_scan_input",
        on_change=handle_multi_add_scan_change,
    )
    ensure_isbn_auto_trigger("ISBN/EAN (scanner codice a barre)")
    if add_col.button("Aggiungi", key="multi-add-add-btn", use_container_width=True):
        if process_scanned_code():
            st.rerun()

    cart = dict(st.session_state.get("multi_add_cart", {}))
    if cart:
        st.markdown("### Elenco aggiunta")
        for entry_key in list(cart.keys()):
            entry = cart.get(entry_key) or {}
            mode = entry.get("mode")
            quantity = int(entry.get("quantity", 0) or 0)
            if quantity <= 0:
                cart.pop(entry_key, None)
                continue

            if mode == "existing":
                book = controller.repository.get_book(str(entry.get("book_id") or ""))
                if not book:
                    cart.pop(entry_key, None)
                    continue
                entry["book"] = book
            else:
                book = entry.get("book")
                if not isinstance(book, Book):
                    cart.pop(entry_key, None)
                    continue

            img_col, line_col, qty_col, del_col = st.columns([1, 5, 2, 1])
            with img_col:
                st.image(_cover_image_source(book), width=54)
            line_col.markdown(f"**{book.normalized_title or book.raw_title}**")
            line_col.caption(book.author or "Autore sconosciuto")
            qty_col.caption(f"Qta {quantity}")
            if del_col.button("X", key=f"multi-add-delete-{entry_key}"):
                cart.pop(entry_key, None)
                st.session_state["multi_add_cart"] = cart
                st.rerun()

        st.session_state["multi_add_cart"] = cart

        add_all_col, clear_col = st.columns(2)
        confirm_add = add_all_col.button("Aggiungi i libri", key="multi-add-confirm", use_container_width=True)
        clear_all = clear_col.button("Svuota", key="multi-add-clear", use_container_width=True)

        if clear_all:
            st.session_state["multi_add_cart"] = {}
            st.rerun()

        if confirm_add:
            added_total = 0
            for entry in cart.values():
                mode = entry.get("mode")
                qty = int(entry.get("quantity", 0) or 0)
                if qty <= 0:
                    continue

                if mode == "existing":
                    latest = controller.repository.get_book(str(entry.get("book_id") or ""))
                    if not latest:
                        continue
                    current_qty = int(getattr(latest, "catalog_quantity", 0) or 0)
                    latest.catalog_quantity = current_qty + qty
                    controller.repository.upsert_book(latest)
                    added_total += qty
                    continue

                prepared = entry.get("book")
                if not isinstance(prepared, Book):
                    continue

                code_value = str(entry.get("code") or getattr(prepared, "catalog_ean", None) or "").strip() or None
                fallback_title = prepared.normalized_title or prepared.raw_title or code_value or ""
                fallback_author = prepared.author
                existing = _find_existing_book_for_manual(
                    fallback_title,
                    fallback_author,
                    code_value,
                )
                if existing is not None:
                    latest = controller.repository.get_book(existing.id)
                    if latest:
                        current_qty = int(getattr(latest, "catalog_quantity", 0) or 0)
                        latest.catalog_quantity = current_qty + qty
                        controller.repository.upsert_book(latest)
                        added_total += qty
                    continue

                selected_candidate = entry.get("candidate") if isinstance(entry.get("candidate"), dict) else None
                inserted: Book | None = None
                try:
                    if selected_candidate is not None:
                        inserted = controller.ingest_selected_candidate(
                            selected_candidate,
                            fallback_title=fallback_title,
                            fallback_author=fallback_author,
                            catalog_ean=code_value,
                            catalog_quantity=qty,
                            catalog_price=None,
                        )
                    else:
                        inserted = controller.ingest_raw_book(
                            fallback_title or (code_value or ""),
                            fallback_author,
                            catalog_ean=code_value,
                            catalog_quantity=qty,
                            catalog_price=None,
                            allow_low_confidence=True,
                        )
                except BookNotFoundError:
                    inserted = controller.ingest_raw_book(
                        fallback_title or (code_value or ""),
                        fallback_author,
                        catalog_ean=code_value,
                        catalog_quantity=qty,
                        catalog_price=None,
                        allow_low_confidence=True,
                    )

                if inserted is not None:
                    added_total += qty

            st.session_state["multi_add_cart"] = {}
            st.session_state["last_multi_add_message"] = f"Inseriti/aggiornati {added_total} libri nel database."
            st.rerun()

    render_isbn_refocus("multi_add", "ISBN/EAN (scanner codice a barre)")
    st.markdown('<a href="?view=dashboard" target="_blank" rel="noopener noreferrer">Torna alla dashboard</a>', unsafe_allow_html=True)


def render_floating_final_db_download_button() -> None:
    queue_books = controller.list_pending()
    queue_df = _approved_books_to_dataframe(queue_books)
    queue_excel = _to_excel_bytes(queue_df, "queue")
    encoded_excel = base64.b64encode(queue_excel).decode("ascii")
    st.markdown(
        f"""
        <div class="floating-download-wrap">
            <a class="floating-download-btn"
               href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{encoded_excel}"
               download="LaCicognaTristeDB.xlsx">
               Download Excel DB
            </a>
            <a class="floating-multi-btn" href="?view=multi-sale" target="_blank" rel="noopener noreferrer">Vendita multipla</a>
            <a class="floating-add-btn" href="?view=multi-add" target="_blank" rel="noopener noreferrer">Aggiunta multipla</a>
            <a class="floating-sales-btn" href="?view=sales" target="_blank" rel="noopener noreferrer">Vendite passate</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_final_db_list() -> None:
    st.markdown("### Lista DB finale")
    approved_books = controller.list_approved()

    if not approved_books:
        return

    st.caption(f"Libri approvati: {len(approved_books)}")

    approved_df = _approved_books_to_dataframe(approved_books)
    approved_excel = _to_excel_bytes(approved_df, "final_db")
    clear_col, download_col = st.columns([1, 3])
    with clear_col:
        if st.button("Svuota DB approvato", key="clear-approved-finaldb", use_container_width=True):
            if hasattr(controller, "clear_approved"):
                removed = controller.clear_approved()
            else:
                removed = controller.approved_repository.clear_books()
            st.success(f"Rimossi {removed} libri dal DB approvato.")
            st.rerun()
    with download_col:
        st.download_button(
            label="Scarica DB finale (Excel)",
            data=approved_excel,
            file_name="biblioforge_final_db.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with st.expander("Mostra/Nascondi lista DB finale", expanded=False):
        for idx, book in enumerate(approved_books, start=1):
            title = book.normalized_title or book.raw_title or "Titolo sconosciuto"
            author = book.author or "Autore sconosciuto"
            isbn = getattr(book, "isbn", None) or "-"
            year = getattr(book, "publication_year", None) or "-"
            rating = f"{book.average_rating:.2f}" if getattr(book, "average_rating", None) is not None else "-"
            tags = ", ".join((book.insights.tags if book.insights else [])[:6]) or "-"

            row_left, row_right = st.columns([6, 1])
            with row_right:
                if st.button("X", key=f"final-remove-{book.id}", use_container_width=True):
                    restored = controller.restore_from_approved(book.id)
                    if restored:
                        st.success("Libro spostato nuovamente nella coda di revisione.")
                    else:
                        st.error("Impossibile spostare il libro selezionato nella coda di revisione.")
                    st.rerun()

            with row_left:
                with st.expander(f"{idx}. {title} - {author}", expanded=False):
                    top_left, top_right = st.columns([1, 3])
                    with top_left:
                        st.image(_cover_image_source(book), width=120)
                    with top_right:
                        st.markdown(f"**Titolo:** {title}")
                        st.markdown(f"**Autore:** {author}")
                        st.markdown(f"**ISBN:** {isbn}")
                        st.markdown(f"**Anno:** {year}")
                        st.markdown(f"**Valutazione:** {rating}")
                        st.markdown(f"**Tag:** {tags}")


def main():
    current_view = st.query_params.get("view", "dashboard")
    if isinstance(current_view, list):
        current_view = current_view[0] if current_view else "dashboard"

    sync_books_file_state()
    ensure_sheets_scheduler_running()

    if current_view == "multi-sale":
        render_centered_title_with_logo()
        render_multi_sale_screen()
        return

    if current_view == "multi-add":
        render_centered_title_with_logo()
        render_multi_add_screen()
        return

    if current_view == "sales":
        render_centered_title_with_logo()
        render_sales_history_screen()
        return

    process_pending_approval()
    if "auto_metadata_checked_ids" not in st.session_state:
        st.session_state["auto_metadata_checked_ids"] = []

    render_centered_title_with_logo()
    left_ingest_col, right_ingest_col = st.columns(2)
    with left_ingest_col:
        render_ingestion_box()
    with right_ingest_col:
        render_excel_ingestion_box()

    if st.session_state.get("last_reject_message"):
        st.warning(st.session_state["last_reject_message"])
        st.session_state["last_reject_message"] = ""

    if st.session_state.get("last_approve_message"):
        st.success(st.session_state["last_approve_message"])
        st.session_state["last_approve_message"] = ""

    if st.session_state.get("last_manual_insert_message"):
        st.success(st.session_state["last_manual_insert_message"])
        st.session_state["last_manual_insert_message"] = ""

    pending = controller.list_pending()
    if not pending:
        st.info("Nessun libro nel database. Aggiungine uno sopra manualmente o importali da Excel per iniziare.")
        render_floating_final_db_download_button()
        return

    st.markdown("Selezione libro dal database")
    pending_ids = [book.id for book in pending]
    apply_pending_selected_book(pending_ids)
    if st.session_state.get("selected_book_id") not in pending_ids:
        # Fallback only updates the current selection and must not queue a stale
        # pending selection, otherwise the first manual dropdown change is overridden.
        st.session_state.pop("pending_selected_book_id", None)
        st.session_state["selected_book_id"] = pending_ids[0]

    title_counts = Counter(_selection_base_title(book).casefold() for book in pending)
    selection_labels = {book.id: _selection_label(book, title_counts) for book in pending}

    selected_id = st.selectbox(
        "Selezione libro dal database",
        options=pending_ids,
        format_func=lambda bid: selection_labels.get(bid, bid),
        label_visibility="collapsed",
        key="selected_book_id",
        on_change=mark_book_selection_change,
    )
    book = next(b for b in pending if b.id == selected_id)

    previous_selected_id = st.session_state.get("last_selected_book_id")
    selection_changed = previous_selected_id is not None and previous_selected_id != book.id
    st.session_state["last_selected_book_id"] = book.id

    force_refresh_for_selected = (
        st.session_state.pop("force_metadata_refresh_book_id", None) == book.id
        or selection_changed
    )
    checked_ids = set(st.session_state.get("auto_metadata_checked_ids", []))
    needs_forced_refresh = (
        controller._has_synthetic_summary(book)
        or controller._looks_like_placeholder_cover(getattr(book, "cover_url", None))
        or not bool(
            getattr(book, "info_link", None)
            or getattr(book, "canonical_volume_link", None)
            or getattr(book, "goodreads_link", None)
            or getattr(book, "openlibrary_key", None)
        )
    )

    if force_refresh_for_selected or book.id not in checked_ids or needs_forced_refresh:
        original_title = _selection_base_title(book)
        original_author = (book.author or "Autore sconosciuto").strip()
        original_code = _selection_code(book)
        try:
            with st.spinner("Recupero metadati iniziali..."):
                refreshed = controller.ensure_review_metadata(book.id)
            if refreshed:
                book = refreshed
        except Exception as exc:
            st.warning(f"Metadati non aggiornati per questo libro: {exc}")
        checked_ids.add(book.id)
        st.session_state["auto_metadata_checked_ids"] = list(checked_ids)

        # If refresh changed visible selector fields, rerun once to update dropdown labels.
        refreshed_title = _selection_base_title(book)
        refreshed_author = (book.author or "Autore sconosciuto").strip()
        refreshed_code = _selection_code(book)
        if (
            refreshed_title != original_title
            or refreshed_author != original_author
            or refreshed_code != original_code
        ):
            request_selected_book(book.id)
            st.rerun()

    left, right = st.columns([1, 1])
    with left:
        render_context_column(book)
    with right:
        render_editing_column(book)

    render_floating_final_db_download_button()


if __name__ == "__main__":
    main()
