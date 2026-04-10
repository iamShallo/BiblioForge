import time
import base64
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import pandas as pd
import streamlit as st

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
    </style>
    """,
    unsafe_allow_html=True,
)


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
    st.markdown("### Contesto e dati estratti")
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
    if catalog_price is not None:
        metric_items.append(("Prezzo catalogo", f"EUR {catalog_price:.2f}"))

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
    st.markdown("### Modifica report")
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
            st.session_state[f"show-remove-popup-{book.id}"] = True
            st.rerun()
        if reject:
            with st.spinner("Rifiuto e rigenerazione in corso..."):
                updated = controller.reject_and_retry(book.id)
            if updated:
                st.session_state["last_reject_message"] = "Libro rifiutato e rigenerato con una nuova analisi crawl + AI."
                st.rerun()
            else:
                st.error("Rifiuto non riuscito: libro selezionato non trovato.")

        if add_quantity:
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
    if "show_isbn_ean_fallback" not in st.session_state:
        st.session_state["show_isbn_ean_fallback"] = False
    if "ingestion_error_message" not in st.session_state:
        st.session_state["ingestion_error_message"] = ""
    if "ingest_candidates" not in st.session_state:
        st.session_state["ingest_candidates"] = []
    if "ingest_input" not in st.session_state:
        st.session_state["ingest_input"] = {}

    if st.session_state.get("ingestion_error_message"):
        st.error(st.session_state["ingestion_error_message"])
        st.session_state["ingestion_error_message"] = ""

    default_title = st.session_state.get("last_failed_title", "The Name of the Rose")
    default_author = st.session_state.get("last_failed_author", "")
    default_catalog_code = st.session_state.get("last_failed_catalog_code", "")

    with st.form("ingestion-form"):
        title = st.text_input("Titolo grezzo", value=default_title)
        author = st.text_input("Autore (opzionale)", value=default_author)
        catalog_code = st.text_input("ISBN o EAN (opzionale)", value=default_catalog_code)
        st.caption("Puoi cercare per titolo, per ISBN/EAN, oppure combinando titolo + autore + ISBN/EAN.")

        if st.session_state.get("show_isbn_ean_fallback"):
            st.warning("Libro non trovato. Come ultima risorsa, inserisci ISBN o EAN per risolvere l'edizione esatta.")

        submitted = st.form_submit_button("Trova corrispondenze")
        if submitted:
            st.session_state["ingestion_error_message"] = ""
            query_title = (title or "").strip() or (catalog_code or "").strip()
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
                try:
                    book = controller.ingest_raw_book(
                        query_title,
                        author or None,
                        catalog_ean=catalog_code or None,
                    )
                    st.success(f"Libro inserito in coda per la revisione: {book.normalized_title}")
                    st.session_state["show_isbn_ean_fallback"] = False
                    st.session_state["last_failed_title"] = "The Name of the Rose"
                    st.session_state["last_failed_author"] = ""
                    st.session_state["last_failed_catalog_code"] = ""
                    st.session_state["ingest_candidates"] = []
                    st.session_state["ingest_input"] = {}
                except BookNotFoundError as exc:
                    st.session_state["show_isbn_ean_fallback"] = True
                    st.session_state["last_failed_title"] = title
                    st.session_state["last_failed_author"] = author
                    st.session_state["last_failed_catalog_code"] = catalog_code
                    st.session_state["ingestion_error_message"] = str(exc)
                    st.rerun()
            else:
                st.session_state["show_isbn_ean_fallback"] = True
                st.session_state["last_failed_title"] = title
                st.session_state["last_failed_author"] = author
                st.session_state["last_failed_catalog_code"] = catalog_code
                st.session_state["ingestion_error_message"] = (
                    "Nessun candidato trovato. Aggiungi autore o ISBN/EAN per restringere la ricerca."
                )
                st.rerun()

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
            try:
                if selected:
                    book = controller.ingest_selected_candidate(
                        selected,
                        fallback_title=ingest_input.get("title"),
                        fallback_author=ingest_input.get("author"),
                        catalog_ean=ingest_input.get("catalog_ean") or None,
                    )
                else:
                    book = controller.ingest_raw_book(
                        sel_title or ingest_input.get("title"),
                        sel_author or None,
                        catalog_ean=ingest_input.get("catalog_ean") or None,
                        allow_low_confidence=True,
                    )
                st.success(f"Libro inserito in coda per la revisione: {book.normalized_title}")
                st.session_state["show_isbn_ean_fallback"] = False
                st.session_state["ingest_candidates"] = []
                st.session_state["ingest_input"] = {}
                st.session_state["last_failed_title"] = "The Name of the Rose"
                st.session_state["last_failed_author"] = ""
                st.session_state["last_failed_catalog_code"] = ""
            except BookNotFoundError as exc:
                st.session_state["ingestion_error_message"] = str(exc)
                st.rerun()


def render_excel_ingestion_box() -> None:
    st.markdown("### Importa da Excel")
    if "persisted_skipped_entries" not in st.session_state:
        st.session_state["persisted_skipped_entries"] = []
    if "persisted_skipped_report_path" not in st.session_state:
        st.session_state["persisted_skipped_report_path"] = None

    default_path = "biblioforge/data/cleaned/books_cleaned.xlsx"
    with st.form("excel-ingestion-form"):
        excel_path_input = st.text_input("Percorso Excel", value=default_path)
        resolved_path = controller.resolve_excel_path(excel_path_input)
        st.caption(f"Sorgente import risolta: {resolved_path}")
        if not resolved_path.exists():
            st.warning("Il percorso Excel non esiste. Aggiorna il percorso prima di importare.")
        submitted = st.form_submit_button("Carica in excel", use_container_width=True)

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
            total = controller.ingest_books_from_excel(excel_path_input, progress_callback=_on_progress)
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
            <button type="button" class="floating-multi-btn">Vendita multipla</button>
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
    process_pending_approval()
    if "auto_metadata_checked_ids" not in st.session_state:
        st.session_state["auto_metadata_checked_ids"] = []

    st.title("La Cicogna Triste")
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

    pending = controller.list_pending()
    if not pending:
        st.info("Nessun libro in attesa di revisione. Aggiungine uno sopra per iniziare.")
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
