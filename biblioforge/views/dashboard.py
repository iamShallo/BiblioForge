import time
import base64
import json
import tempfile
from pathlib import Path
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from biblioforge.controllers.pipeline_controller import BookNotFoundError, PipelineController
from biblioforge.models.book import Book, BookStatus
from biblioforge.services.normalization_service import normalize_title


controller = PipelineController()
st.set_page_config(page_title="La Cicogna Triste", layout="wide")
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
        for key in [
            "selected_book_id",
            "auto_metadata_checked_ids",
            "last_manual_insert_message",
            "last_reject_message",
            "last_approve_message",
            "ingest_candidates",
            "ingest_input",
            "pending_manual_ingest",
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
        st.rerun()


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
    components.html(
        f"""
        <script>
        (function() {{
            const parentWindow = window.parent;
            const label = {escaped_label};
            const selector = 'input[aria-label="' + label + '"]';

            if (!parentWindow.__biblioforgeIsbnWatchers) {{
                parentWindow.__biblioforgeIsbnWatchers = {{}};
            }}

            const existing = parentWindow.__biblioforgeIsbnWatchers[label];
            if (existing) {{
                clearInterval(existing);
            }}

            const triggerIfReady = (input) => {{
                if (!input) {{
                    return;
                }}
                const normalized = (input.value || '').replace(/[^0-9A-Za-z]/g, '');
                const lastSent = input.dataset.biblioforgeLastSubmittedIsbn || '';
                if (normalized.length >= 12) {{
                    if (lastSent !== normalized) {{
                        input.dataset.biblioforgeLastSubmittedIsbn = normalized;
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.blur();
                    }}
                }} else {{
                    input.dataset.biblioforgeLastSubmittedIsbn = '';
                }}
            }};

            const tick = () => {{
                const input = parentWindow.document.querySelector(selector);
                if (!input) {{
                    return;
                }}
                if (input.dataset.biblioforgeIsbnImmediateInstalled !== '1') {{
                    input.dataset.biblioforgeIsbnImmediateInstalled = '1';
                    input.addEventListener('input', () => triggerIfReady(input));
                    input.addEventListener('paste', () => setTimeout(() => triggerIfReady(input), 0));
                }}
                triggerIfReady(input);
            }};

            parentWindow.__biblioforgeIsbnWatchers[label] = setInterval(tick, 40);
            tick();
        }})();
        </script>
        """,
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
            st.session_state["selected_book_id"] = refreshed_pending[0].id
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
    catalog_price = getattr(book, "catalog_price", None)

    cols = st.columns([1, 2])
    with cols[0]:
        if book.cover_url:
            st.image(bust_cache(book.cover_url, book.id), width=160)
        else:
            st.image("https://via.placeholder.com/160x240?text=Copertina+assente", width=160)
    with cols[1]:
        st.markdown(f"#### {book.normalized_title}")
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
        edit_price_state_key = f"show-price-editor-{book.id}"
        for idx, (label, value) in enumerate(metric_items):
            target = left_meta if idx % 2 == 0 else right_meta
            if label == "Prezzo catalogo":
                if target.button(
                    f"Prezzo catalogo: {value}",
                    key=f"edit-price-line-{book.id}",
                    help="Clicca per modificare il prezzo",
                ):
                    st.session_state[edit_price_state_key] = True
            else:
                target.markdown(
                    f"<div class='meta-line'><span class='meta-label'>{label}:</span> {value}</div>",
                    unsafe_allow_html=True,
                )

    if st.session_state.get(edit_price_state_key):
        st.markdown("##### Modifica prezzo catalogo")
        with st.form(key=f"edit-price-form-{book.id}"):
            new_price = st.number_input(
                "Nuovo prezzo catalogo (EUR)",
                min_value=0.0,
                value=float(catalog_price or 0.0),
                step=0.5,
                format="%.2f",
            )
            save_col, cancel_col = st.columns(2)
            save_price = save_col.form_submit_button("Salva", use_container_width=True)
            cancel_price = cancel_col.form_submit_button("Annulla", use_container_width=True)

        if cancel_price:
            st.session_state.pop(edit_price_state_key, None)
            st.rerun()

        if save_price:
            latest = controller.repository.get_book(book.id)
            if latest is None:
                st.error("Libro non trovato nel DB.")
            else:
                latest.catalog_price = float(new_price)
                controller.repository.upsert_book(latest)
                st.success(f"Prezzo catalogo aggiornato: EUR {float(new_price):.2f}")
            st.session_state.pop(edit_price_state_key, None)
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

    if book.average_rating is not None:
        if book.average_rating <= 2.0:
            color = "#c23b22"  # red
        elif book.average_rating <= 4.0:
            color = "#d97706"  # orange
        else:
            color = "#1b8f3b"  # green

        rating_html = f"<span style='color:{color}; font-size:30px; font-weight:800;'>{book.average_rating:.2f}</span>"
        details = ["Valutazione Goodreads"]
        if book.ratings_count:
            details.append(f"{book.ratings_count:,} valutazioni")
        st.markdown(f"{rating_html} &nbsp; {' · '.join(details)}", unsafe_allow_html=True)

    if book.review_samples:
        st.markdown("### Esempi di recensioni")
        preview_chars = 260
        for idx, sample in enumerate(book.review_samples):
            full_text = (sample.text or "").strip()
            expanded_key = f"review-expanded-{book.id}-{idx}"
            if expanded_key not in st.session_state:
                st.session_state[expanded_key] = False

            is_long = len(full_text) > preview_chars
            shown_text = full_text
            if is_long and not st.session_state[expanded_key]:
                shown_text = full_text[:preview_chars].rsplit(" ", 1)[0] + "..."

            st.markdown(f"- **{sample.reviewer}** ({sample.rating:.1f}/5)")
            st.markdown(shown_text)

            if is_long:
                toggle_label = "Riduci" if st.session_state[expanded_key] else "Espandi"
                if st.button(toggle_label, key=f"{expanded_key}-toggle"):
                    st.session_state[expanded_key] = not st.session_state[expanded_key]
                    st.rerun()
    else:
        st.warning("Nessun dato di recensioni utente disponibile per questo libro.")

    # Rejected-information audit remains stored in data, but is intentionally hidden in UI.


def render_editing_column(book: Book) -> None:
    if not book.insights:
        st.warning("Nessun insight AI disponibile per questo libro.")
        return

    with st.form(key=f"editing-form-{book.id}"):
        summary = st.text_area("Riassunto", value=book.insights.summary, height=180)
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
            st.session_state[f"show-remove-popup-{book.id}"] = True
            st.rerun()
        if reject:
            with st.spinner("Cerco i dati online..."):
                updated = controller.reject_and_retry(book.id)
            if updated:
                st.session_state["last_reject_message"] = "Libro rigenerato con una nuova analisi crawl+AI"
                st.rerun()
            else:
                st.error("Rifiuto non riuscito: libro selezionato non trovato.")

        if add_quantity:
            st.session_state.pop(f"show-remove-popup-{book.id}", None)
            st.session_state[f"show-quantity-popup-{book.id}"] = True
            st.rerun()

    if st.session_state.get(f"show-remove-popup-{book.id}"):
        with st.form(key=f"remove-price-form-{book.id}"):
            st.markdown("### Rimuovi dalla lista")
            st.warning("Sei sicuro?")
            confirm_col, cancel_col = st.columns(2)
            confirm_remove = confirm_col.form_submit_button("Conferma rimozione", use_container_width=True)
            cancel_remove = cancel_col.form_submit_button("Annulla", use_container_width=True)

        if cancel_remove:
            st.session_state.pop(f"show-remove-popup-{book.id}", None)
            st.rerun()

        if confirm_remove:
            latest = controller.repository.get_book(book.id)
            if not latest:
                st.error("Libro non trovato in archivio.")
                st.session_state.pop(f"show-remove-popup-{book.id}", None)
                st.rerun()

            current_qty = int(getattr(latest, "catalog_quantity", 0) or 0)
            new_qty = current_qty - 1

            if new_qty < 1:
                if hasattr(controller, "remove_from_queue"):
                    removed = controller.remove_from_queue(book.id)
                elif hasattr(controller.repository, "delete_book"):
                    # Fallback for stale Streamlit state with an older controller instance.
                    removed = controller.repository.delete_book(book.id)
                else:
                    # Final fallback for older repository objects loaded before method additions.
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
                    st.success("Quantità arrivata a 0: libro rimosso dal DB.")
                    st.session_state.pop(f"show-remove-popup-{book.id}", None)
                    st.rerun()
                else:
                    st.error("Impossibile rimuovere il libro selezionato dalla coda.")
            else:
                latest.catalog_quantity = new_qty
                controller.repository.upsert_book(latest)
                st.success(f"Quantità ridotta di 1. Quantità totale nel catalogo: {new_qty}.")
                st.session_state.pop(f"show-remove-popup-{book.id}", None)
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
    if "pending_manual_ingest" not in st.session_state:
        st.session_state["pending_manual_ingest"] = None
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

        if not force and not catalog_code:
            return

        st.session_state["ingestion_error_message"] = ""
        query_title = title or catalog_code
        existing = _find_existing_book_for_manual(query_title, author or None, catalog_code or None)
        if catalog_code and existing is not None:
            st.session_state["pending_manual_ingest"] = {
                "mode": "direct",
                "title": query_title,
                "author": author or None,
                "catalog_ean": catalog_code or None,
                "existing_book_id": existing.id,
                "default_price": float(getattr(existing, "catalog_price", 0.0) or 0.0),
            }
            st.session_state["show_isbn_ean_fallback"] = False
            st.session_state["manual_clear_input_next_run"] = True
            request_isbn_refocus("manual")
            return

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
        if candidates:
            st.session_state["show_isbn_ean_fallback"] = False
        elif catalog_code:
            st.session_state["pending_manual_ingest"] = {
                "mode": "direct",
                "title": query_title,
                "author": author or None,
                "catalog_ean": catalog_code or None,
                "existing_book_id": existing.id if existing else None,
                "default_price": float(getattr(existing, "catalog_price", 0.0) or 0.0),
            }
            st.session_state["show_isbn_ean_fallback"] = False
            st.session_state["manual_clear_input_next_run"] = True
            request_isbn_refocus("manual")
            st.rerun()
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
        st.session_state["manual_ingest_catalog_code"] = ""
        st.session_state["manual_last_autosearch_code"] = ""
        st.session_state["manual_clear_input_next_run"] = False

    title = st.text_input("Titolo", key="manual_ingest_title")
    author = st.text_input("Autore (opzionale)", key="manual_ingest_author")
    catalog_code = st.text_input("ISBN o EAN", key="manual_ingest_catalog_code")
    ensure_isbn_auto_trigger("ISBN o EAN")
    manual_scan_code = _normalize_code(catalog_code)
    if len(manual_scan_code) >= 12 and manual_scan_code != st.session_state.get("manual_last_autosearch_code", ""):
        st.session_state["manual_last_autosearch_code"] = manual_scan_code
        process_manual_ingestion(force=False)
        st.rerun()
    elif len(manual_scan_code) < 12:
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
            format_func=lambda idx: f"{candidates[idx].get('title') or 'Titolo sconosciuto'} — {candidates[idx].get('authors') or 'Autore sconosciuto'}",
            key="ingest_choice",
        )
        if st.button("Usa selezione e importa", use_container_width=True):
            selected = candidates[choice] if isinstance(choice, int) and choice < len(candidates) else None
            sel_title = selected.get("title") if selected else ingest_input.get("title")
            sel_author = selected.get("authors") if selected else ingest_input.get("author")
            existing = _find_existing_book_for_manual(
                sel_title or ingest_input.get("title"),
                sel_author or None,
                ingest_input.get("catalog_ean") or None,
            )
            st.session_state["pending_manual_ingest"] = {
                "mode": "candidate" if selected else "direct-fallback",
                "selected": selected,
                "fallback_title": ingest_input.get("title"),
                "fallback_author": ingest_input.get("author"),
                "title": sel_title or ingest_input.get("title"),
                "author": sel_author or None,
                "catalog_ean": ingest_input.get("catalog_ean") or None,
                "existing_book_id": existing.id if existing else None,
                "default_price": float(getattr(existing, "catalog_price", 0.0) or 0.0),
            }
            st.rerun()

    pending = st.session_state.get("pending_manual_ingest")
    if pending:
        existing_book_id = pending.get("existing_book_id")
        if existing_book_id:
            existing = controller.repository.get_book(existing_book_id)
            if existing and getattr(existing, "catalog_price", None) is not None:
                current_qty = int(getattr(existing, "catalog_quantity", 0) or 0)
                existing.catalog_quantity = current_qty + 1
                controller.repository.upsert_book(existing)
                st.session_state["last_manual_insert_message"] = (
                    f"Libro inserito nel database: {existing.normalized_title or existing.raw_title} | Quantità aggiornata: {existing.catalog_quantity}"
                )
                st.session_state["selected_book_id"] = existing.id
                st.session_state["pending_manual_ingest"] = None
                st.session_state["show_isbn_ean_fallback"] = False
                st.session_state["ingest_candidates"] = []
                st.session_state["ingest_input"] = {}
                st.session_state["last_failed_title"] = ""
                st.session_state["last_failed_author"] = ""
                st.session_state["last_failed_catalog_code"] = ""
                request_isbn_refocus("manual")
                st.rerun()

        with st.form("manual-price-before-insert"):
            st.markdown("### Prezzo di vendita")
            sale_price = st.number_input(
                "Inserisci il prezzo di vendita (EUR)",
                min_value=0.01,
                value=float(pending.get("default_price") or 0.0) or 0.01,
                step=0.5,
                format="%.2f",
            )
            confirm_col, cancel_col = st.columns(2)
            confirm_insert = confirm_col.form_submit_button("Conferma inserimento", use_container_width=True)
            cancel_insert = cancel_col.form_submit_button("Annulla", use_container_width=True)

        if cancel_insert:
            st.session_state["pending_manual_ingest"] = None
            st.rerun()

        if confirm_insert:
            try:
                mode = pending.get("mode")
                existing_book_id = pending.get("existing_book_id")
                if existing_book_id:
                    latest = controller.repository.get_book(existing_book_id)
                    if not latest:
                        st.error("Libro non trovato nel DB.")
                        st.session_state["pending_manual_ingest"] = None
                        st.rerun()

                    current_qty = int(getattr(latest, "catalog_quantity", 0) or 0)
                    latest.catalog_quantity = current_qty + 1
                    if getattr(latest, "catalog_price", None) is None:
                        latest.catalog_price = float(sale_price)
                    controller.repository.upsert_book(latest)
                    st.session_state["last_manual_insert_message"] = (
                        f"Libro inserito nel database: {latest.normalized_title or latest.raw_title} | Quantità aggiornata: {latest.catalog_quantity}"
                    )
                    st.session_state["selected_book_id"] = latest.id
                else:
                    if mode == "candidate" and pending.get("selected") is not None:
                        book = controller.ingest_selected_candidate(
                            pending.get("selected"),
                            fallback_title=pending.get("fallback_title"),
                            fallback_author=pending.get("fallback_author"),
                            catalog_ean=pending.get("catalog_ean") or None,
                            catalog_quantity=1,
                            catalog_price=float(sale_price),
                        )
                    else:
                        book = controller.ingest_raw_book(
                            pending.get("title") or "",
                            pending.get("author") or None,
                            catalog_ean=pending.get("catalog_ean") or None,
                            catalog_quantity=1,
                            catalog_price=float(sale_price),
                            allow_low_confidence=(mode == "direct-fallback"),
                        )

                    st.session_state["last_manual_insert_message"] = (
                        f"Libro inserito nel database: {book.normalized_title} | Prezzo vendita: EUR {float(sale_price):.2f}"
                    )
                    st.session_state["selected_book_id"] = book.id
                st.session_state["pending_manual_ingest"] = None
                st.session_state["show_isbn_ean_fallback"] = False
                st.session_state["ingest_candidates"] = []
                st.session_state["ingest_input"] = {}
                st.session_state["last_failed_title"] = ""
                st.session_state["last_failed_author"] = ""
                st.session_state["last_failed_catalog_code"] = ""
                request_isbn_refocus("manual")
                st.rerun()
            except BookNotFoundError as exc:
                st.session_state["ingestion_error_message"] = str(exc)
                request_isbn_refocus("manual")
                st.rerun()

    render_isbn_refocus("manual", "ISBN o EAN")


def render_excel_ingestion_box() -> None:
    st.markdown("### Importa da Excel")
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

    timer_placeholder = st.empty()
    progress_placeholder = st.empty()
    if submitted:
        start = time.perf_counter()
        timer_placeholder.info("Import in corso...")
        progress_bar = progress_placeholder.progress(0, text="Preparazione import...")

        def _on_progress(processed: int, total: int) -> None:
            pct = 0 if total == 0 else int((processed / total) * 100)
            pct = max(0, min(pct, 100))
            text = f"Import in corso... {processed}/{total}" if total else "Import in corso..."
            progress_bar.progress(pct, text=text)

        try:
            import_source = st.session_state.get("uploaded_excel_temp_path")
            if not import_source:
                raise FileNotFoundError("Nessun file Excel selezionato.")

            total = controller.ingest_books_from_excel(import_source, progress_callback=_on_progress)
            progress_bar.progress(100, text="Import completato")
            st.success(f"Importati {total} libri nella coda di revisione.")
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
            
            timer_placeholder.success(f"Import completato in {format_duration(time.perf_counter() - start)}")
        except Exception as exc:
            progress_bar.progress(0.0, text="Import fallito")
            timer_placeholder.error(
                f"Import fallito dopo {format_duration(time.perf_counter() - start)}: {exc}"
            )
            st.error(f"Import da Excel fallito: {exc}")

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
    rows = []
    for book in approved_books:
        categories = ", ".join(getattr(book, "categories", []) or [])
        rows.append(
            {
                "Title": book.normalized_title or book.raw_title,
                "Author": book.author,
                "Primary Image": getattr(book, "cover_url", None),
                "Prezzo": getattr(book, "catalog_price", None),
                "ISBN": getattr(book, "isbn", None),
                "Publication Date": getattr(book, "published_date", None),
                "Number of pages": getattr(book, "pages", None),
                "Categoria": categories,
                "Content Summary": book.insights.summary if book.insights else None,
                "Catalog Quantity": getattr(book, "catalog_quantity", None),
                "Average Rating": getattr(book, "average_rating", None),
            }
        )
    return pd.DataFrame(rows)


def _normalize_code(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def _find_book_by_isbn(code: str) -> Book | None:
    needle = _normalize_code(code)
    if not needle:
        return None

    for candidate in controller.repository.list_books():
        values = [
            getattr(candidate, "isbn", None),
            getattr(candidate, "isbn_10", None),
            getattr(candidate, "catalog_ean", None),
        ]
        if any(_normalize_code(v) == needle for v in values if v):
            return candidate
    return None


def _find_existing_book_for_manual(title: str | None, author: str | None, catalog_ean: str | None) -> Book | None:
    existing_by_code = _find_book_by_isbn(catalog_ean or "")
    if existing_by_code is not None:
        return existing_by_code

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
    st.markdown("## Vendita multipla")
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
        current_in_catalog = int(getattr(found, "catalog_quantity", 0) or 0)
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
    )
    ensure_isbn_auto_trigger("ISBN (scanner codice a barre)")
    multi_sale_scan_code = _normalize_code(st.session_state.get("multi_sale_scan_input"))
    if len(multi_sale_scan_code) >= 12 and multi_sale_scan_code != st.session_state.get("multi_sale_last_autosearch_code", ""):
        st.session_state["multi_sale_last_autosearch_code"] = multi_sale_scan_code
        if process_scanned_isbn():
            st.rerun()
    elif len(multi_sale_scan_code) < 12:
        st.session_state["multi_sale_last_autosearch_code"] = ""
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
                if getattr(book, "cover_url", None):
                    st.image(bust_cache(book.cover_url, book.id), width=54)
                else:
                    st.image("https://via.placeholder.com/54x80?text=No+Cover", width=54)
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
                current_qty = int(getattr(latest, "catalog_quantity", 0) or 0)
                if int(qty) > current_qty:
                    invalid_items.append(latest.normalized_title or latest.raw_title)

            if invalid_items:
                st.error("Quantità richiesta non presente nel catalogo.")
                return

            for book_id, qty in cart.items():
                latest = controller.repository.get_book(book_id)
                if not latest:
                    continue
                current_qty = int(getattr(latest, "catalog_quantity", 0) or 0)
                new_qty = current_qty - int(qty)
                if new_qty < 1:
                    controller.repository.delete_book(book_id)
                else:
                    latest.catalog_quantity = new_qty
                    controller.repository.upsert_book(latest)
            st.session_state["multi_sale_cart"] = {}
            st.session_state["last_multi_sale_message"] = "Vendita multipla registrata."
            st.rerun()

    render_isbn_refocus("multi_sale", "ISBN (scanner codice a barre)")

    st.markdown("[Torna alla dashboard](?view=dashboard)")


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
            <a class="floating-multi-btn" href="?view=multi-sale">Vendita multipla</a>
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
                        if getattr(book, "cover_url", None):
                            st.image(bust_cache(book.cover_url, book.id), width=120)
                        else:
                            st.image("https://via.placeholder.com/120x180?text=Copertina+assente", width=120)
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

    if current_view == "multi-sale":
        render_centered_title_with_logo()
        render_multi_sale_screen()
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
    if st.session_state.get("selected_book_id") not in pending_ids:
        st.session_state["selected_book_id"] = pending_ids[0]

    selected_id = st.selectbox(
        "Selezione libro dal database",
        options=pending_ids,
        format_func=lambda bid: next(
            (normalize_title(b.raw_title or b.normalized_title, b.author) for b in pending if b.id == bid),
            bid,
        ),
        label_visibility="collapsed",
        key="selected_book_id",
    )
    book = next(b for b in pending if b.id == selected_id)

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

    if book.id not in checked_ids or needs_forced_refresh:
        with st.spinner("Recupero metadati iniziali..."):
            refreshed = controller.ensure_review_metadata(book.id)
        if refreshed:
            book = refreshed
        checked_ids.add(book.id)
        st.session_state["auto_metadata_checked_ids"] = list(checked_ids)

    left, right = st.columns([1, 1])
    with left:
        render_context_column(book)
    with right:
        render_editing_column(book)

    render_floating_final_db_download_button()


if __name__ == "__main__":
    main()
