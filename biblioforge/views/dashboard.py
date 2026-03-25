import time
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import pandas as pd
import streamlit as st

from biblioforge.controllers.pipeline_controller import BookNotFoundError, PipelineController
from biblioforge.models.book import Book, BookStatus
from biblioforge.services.normalization_service import normalize_title


controller = PipelineController()
st.set_page_config(page_title="BiblioForge", layout="wide")
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
    </style>
    """,
    unsafe_allow_html=True,
)


def process_pending_approval() -> None:
    """Run a queued approval (set in session) outside the form to avoid double clicks."""
    request = st.session_state.get("approve_request")
    if not request:
        return

    with st.spinner("Saving and approving..."):
        approved_book = controller.approve_with_edits(
            request.get("book_id"),
            request.get("summary", ""),
            request.get("tags", []),
        )

    if not approved_book:
        st.session_state["last_approve_message"] = "Could not approve: book not found or already processed."
    else:
        refreshed_pending = controller.list_pending()
        if refreshed_pending:
            st.session_state["selected_book_id"] = refreshed_pending[0].id
        else:
            st.session_state.pop("selected_book_id", None)

        st.session_state["last_approve_message"] = "Book approved and saved to the new final DB."

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
        BookStatus.TO_CLEAN: "To Clean",
        BookStatus.IN_PROGRESS: "In Progress",
        BookStatus.TO_APPROVE: "To Approve",
        BookStatus.APPROVED: "Approved",
    }
    return labels.get(status, status.value)


def render_context_column(book: Book) -> None:
    st.markdown("### Context & Extracted Data")
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
            st.image("https://via.placeholder.com/160x240?text=No+Cover", width=160)
    with cols[1]:
        st.markdown(f"#### {book.normalized_title}")
        st.caption(book.author or "Unknown Author")
        st.button("AI_PROCESSED", disabled=True, use_container_width=False)
        st.caption(f"Current status: {status_label(book.status)}")

    st.markdown("---")
    metric_items = []
    if catalog_ean:
        metric_items.append(("Catalog EAN", str(catalog_ean)))
    if catalog_publisher:
        metric_items.append(("Catalog Publisher", str(catalog_publisher)))
    if catalog_quantity is not None:
        metric_items.append(("Catalog Quantity", str(catalog_quantity)))
    if catalog_price is not None:
        metric_items.append(("Catalog Price", f"EUR {catalog_price:.2f}"))

    if book.publication_year:
        metric_items.append(("Edition Year", str(book.publication_year)))
    if first_publish_year:
        metric_items.append(("First Publish Year", str(first_publish_year)))
    if published_date:
        metric_items.append(("Published Date", str(published_date)))
    if book.pages:
        metric_items.append(("Pages", str(book.pages)))
    if book.isbn:
        metric_items.append(("ISBN", str(book.isbn)))
    if isbn_10:
        metric_items.append(("ISBN-10", str(isbn_10)))
    if edition_count:
        metric_items.append(("Edition Count", str(edition_count)))
    if book.publisher:
        metric_items.append(("API Publisher", book.publisher))
    if language:
        metric_items.append(("Language", language))
    if print_type:
        metric_items.append(("Print Type", print_type))
    if openlibrary_key:
        metric_items.append(("OpenLibrary Key", openlibrary_key))

    if metric_items:
        st.markdown("#### Metadata")
        left_meta, right_meta = st.columns(2)
        for idx, (label, value) in enumerate(metric_items):
            target = left_meta if idx % 2 == 0 else right_meta
            target.markdown(
                f"<div class='meta-line'><span class='meta-label'>{label}:</span> {value}</div>",
                unsafe_allow_html=True,
            )

    if book.summary_source:
        st.caption(f"Summary Source: {book.summary_source}")
    if categories:
        st.caption(f"Categories: {', '.join(categories)}")
    source_links = [
        ("Google Books Info", info_link),
        ("Google Books Preview", preview_link),
        ("Canonical Volume Page", canonical_volume_link),
        ("Goodreads Page", goodreads_link),
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
        st.caption(f"Reject attempts: {reject_attempts}")

    if book.average_rating is not None:
        if book.average_rating <= 2.0:
            color = "#c23b22"  # red
        elif book.average_rating <= 4.0:
            color = "#d97706"  # orange
        else:
            color = "#1b8f3b"  # green

        rating_html = f"<span style='color:{color}; font-size:30px; font-weight:800;'>{book.average_rating:.2f}</span>"
        details = ["Goodreads rating"]
        if book.ratings_count:
            details.append(f"{book.ratings_count:,} ratings")
        st.markdown(f"{rating_html} &nbsp; {' · '.join(details)}", unsafe_allow_html=True)

    if book.review_samples:
        st.markdown("### Review Samples")
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
                toggle_label = "Collapse" if st.session_state[expanded_key] else "Expand"
                if st.button(toggle_label, key=f"{expanded_key}-toggle"):
                    st.session_state[expanded_key] = not st.session_state[expanded_key]
                    st.rerun()
    else:
        st.warning("No user review data available for this book.")

    # Rejected-information audit remains stored in data, but is intentionally hidden in UI.


def render_editing_column(book: Book, pending_ids: list[str]) -> None:
    st.markdown("### Report Editing")
    if not book.insights:
        st.warning("No AI insights available for this book yet.")
        return

    with st.form(key=f"editing-form-{book.id}"):
        summary = st.text_area("Summary", value=book.insights.summary, height=180)
        tags = st.multiselect(
            "Tags",
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
        approve = col_approve.form_submit_button("Approve and Save", use_container_width=True)
        reject = col_reject.form_submit_button("Reject & Redo Search", use_container_width=True)
        remove = col_remove.form_submit_button("Remove", use_container_width=True)

        if approve:
            st.session_state["approve_request"] = {
                "book_id": book.id,
                "summary": summary,
                "tags": tags,
            }
            st.rerun()
        if reject:
            with st.spinner("Rejecting and regenerating..."):
                updated = controller.reject_and_retry(book.id)
            if updated:
                st.session_state["last_reject_message"] = "Book rejected and regenerated with a fresh crawl + AI pass."
                st.rerun()
            else:
                st.error("Reject failed: selected book was not found.")
        if remove:
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
                st.success("Book removed from the review queue.")
                st.rerun()
            else:
                st.error("Could not remove the selected book from the queue.")

    trust_col = st.container()
    remaining = len(pending_ids)
    trust_col.caption(f"Pending to approve: {remaining}")
    if trust_col.button("Trust the Process", help="Approve all pending books in one batch."):
        progress_placeholder = st.empty()
        progress_bar = progress_placeholder.progress(0, text="Starting process...")
        
        def _on_progress(processed: int, total: int) -> None:
            pct = 0 if total == 0 else int((processed / total) * 100)
            pct = max(0, min(pct, 100))
            text = f"Processing books... {processed}/{total}"
            progress_bar.progress(pct, text=text)
        
        approved = controller.trust_process(progress_callback=_on_progress)
        progress_bar.progress(100, text="Process completed!")
        st.success(f"Process trusted: {approved} books saved to the final DB in one batch.")


def render_ingestion_box():
    st.markdown("### Add a Book")
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
        title = st.text_input("Raw Title", value=default_title)
        author = st.text_input("Author (optional)", value=default_author)
        catalog_code = st.text_input("ISBN or EAN (optional)", value=default_catalog_code)
        st.caption("You can search by title, by ISBN/EAN, or by combining title + author + ISBN/EAN.")

        if st.session_state.get("show_isbn_ean_fallback"):
            st.warning("Book not found. As a last resort, insert ISBN or EAN to resolve the exact edition.")

        submitted = st.form_submit_button("Find Matches")
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
                    st.success(f"Book queued for review: {book.normalized_title}")
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
                    "No candidate found. Add author or ISBN/EAN to narrow the search."
                )
                st.rerun()

    # Post-form selection step
    candidates = st.session_state.get("ingest_candidates", [])
    ingest_input = st.session_state.get("ingest_input", {})
    if candidates:
        st.markdown("### Select a match to ingest")
        choice = st.radio(
            "Candidates",
            options=list(range(len(candidates))),
            format_func=lambda idx: f"{candidates[idx].get('title') or 'Unknown title'} — {candidates[idx].get('authors') or 'Unknown author'}",
            key="ingest_choice",
        )
        if st.button("Use selection and ingest", use_container_width=True):
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
                st.success(f"Book queued for review: {book.normalized_title}")
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
    st.markdown("### Import from Excel")
    if "persisted_skipped_entries" not in st.session_state:
        st.session_state["persisted_skipped_entries"] = []
    if "persisted_skipped_report_path" not in st.session_state:
        st.session_state["persisted_skipped_report_path"] = None

    default_path = "biblioforge/data/cleaned/books_cleaned.xlsx"
    excel_path_input = st.text_input("Excel path", value=default_path)
    resolved_path = controller.resolve_excel_path(excel_path_input)
    st.caption(f"Resolved import source: {resolved_path}")
    if not resolved_path.exists():
        st.warning("Excel path does not exist. Update the path before importing.")
    timer_placeholder = st.empty()
    progress_placeholder = st.empty()
    if st.button("Load into review queue", use_container_width=True):
        start = time.perf_counter()
        timer_placeholder.info("⏱️ Import in progress...")
        progress_bar = progress_placeholder.progress(0, text="Preparing import...")

        def _on_progress(processed: int, total: int) -> None:
            pct = 0 if total == 0 else int((processed / total) * 100)
            pct = max(0, min(pct, 100))
            text = f"Import in progress... {processed}/{total}" if total else "Import in progress..."
            progress_bar.progress(pct, text=text)

        try:
            total = controller.ingest_books_from_excel(excel_path_input, progress_callback=_on_progress)
            progress_bar.progress(100, text="Import completed")
            st.success(f"Imported {total} books into review queue.")
            if getattr(controller, "last_import_skipped", 0):
                skipped_count = controller.last_import_skipped
                st.warning(
                    f"Skipped {skipped_count} rows because the book could not be resolved confidently."
                )
            st.session_state["persisted_skipped_entries"] = list(
                getattr(controller, "last_import_skipped_details", []) or []
            )
            st.session_state["persisted_skipped_report_path"] = getattr(
                controller,
                "last_import_skipped_report_path",
                None,
            )
            
            timer_placeholder.success(f"⏱️ Import completed in {format_duration(time.perf_counter() - start)}")
        except Exception as exc:
            progress_bar.progress(0.0, text="Import failed")
            timer_placeholder.error(
                f"⏱️ Import failed after {format_duration(time.perf_counter() - start)}: {exc}"
            )
            st.error(f"Excel import failed: {exc}")

    skipped_details = st.session_state.get("persisted_skipped_entries", [])
    skipped_report_path = st.session_state.get("persisted_skipped_report_path")

    if skipped_details:
        top_left, top_mid, top_right = st.columns([3, 2, 1])
        top_left.warning(
            f"Persistent skipped entries: {len(skipped_details)} rows not resolved automatically."
        )
        retry_clicked = top_mid.button("Retry all skipped", use_container_width=True)
        if top_right.button("Clear skipped list", use_container_width=True):
            st.session_state["persisted_skipped_entries"] = []
            st.session_state["persisted_skipped_report_path"] = None
            st.rerun()

        if retry_clicked:
            progress = st.progress(0, text="Retry skipped in progress...")
            def _on_retry_progress(processed: int, total: int) -> None:
                pct = 0 if total == 0 else int((processed / total) * 100)
                pct = max(0, min(pct, 100))
                text = f"Retry skipped... {processed}/{total}" if total else "Retry skipped in progress..."
                progress.progress(pct, text=text)

            resolved, still_skipped = controller.retry_skipped_entries(
                skipped_details,
                progress_callback=_on_retry_progress,
            )

            progress.progress(100, text="Retry skipped completed")
            st.session_state["persisted_skipped_entries"] = still_skipped
            if resolved:
                st.success(f"Retry completed: resolved {resolved} entries.")
            if still_skipped:
                st.warning(f"Still unresolved: {len(still_skipped)} entries.")
            st.rerun()

        skipped_df = _skipped_entries_to_dataframe(skipped_details)
        skipped_excel = _to_excel_bytes(skipped_df, "skipped")
        st.download_button(
            label="Download Skipped List (Excel)",
            data=skipped_excel,
            file_name="biblioforge_skipped_list.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        with st.expander(f"📋 View skipped entries ({len(skipped_details)} items)", expanded=True):
            st.subheader("Skipped Books")
            for idx, entry in enumerate(skipped_details, 1):
                entry_title = (entry.get("title") or "").strip()
                entry_author = (entry.get("author") or "").strip()
                entry_ean = str(entry.get("ean") or "").strip()

                st.caption(f"{idx}. **{entry.get('title', 'Unknown')}**")
                st.caption(f"Author: {entry_author or 'Unknown Author'}")
                if entry_ean:
                    st.caption(f"EAN: {entry_ean}")
                reason = entry.get("reason", "Unknown reason")
                st.caption(f"Reason: {reason}")

                st.divider()

    if skipped_report_path:
        try:
            import os

            if os.path.exists(skipped_report_path):
                with open(skipped_report_path, "r", encoding="utf-8") as f:
                    report_content = f.read()
                st.download_button(
                    label="📥 Download Skipped Report (JSON)",
                    data=report_content,
                    file_name=os.path.basename(skipped_report_path),
                    mime="application/json",
                )
        except Exception as e:
            st.warning(f"Could not load report file: {e}")


def _to_excel_bytes(dataframe: pd.DataFrame, sheet_name: str) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name=sheet_name)
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
        tags = ", ".join((book.insights.tags if book.insights else []) or [])
        rows.append(
            {
                "id": book.id,
                "title": book.normalized_title or book.raw_title,
                "raw_title": book.raw_title,
                "author": book.author,
                "isbn": getattr(book, "isbn", None),
                "isbn_10": getattr(book, "isbn_10", None),
                "publication_year": getattr(book, "publication_year", None),
                "published_date": getattr(book, "published_date", None),
                "publisher": getattr(book, "publisher", None),
                "catalog_publisher": getattr(book, "catalog_publisher", None),
                "catalog_ean": getattr(book, "catalog_ean", None),
                "catalog_quantity": getattr(book, "catalog_quantity", None),
                "catalog_price": getattr(book, "catalog_price", None),
                "average_rating": getattr(book, "average_rating", None),
                "ratings_count": getattr(book, "ratings_count", 0),
                "cover_url": getattr(book, "cover_url", None),
                "status": getattr(book.status, "value", None),
                "tags": tags,
                "summary": book.insights.summary if book.insights else None,
            }
        )
    return pd.DataFrame(rows)


def render_final_db_list() -> None:
    st.markdown("### Final DB List")
    approved_books = controller.list_approved()

    if not approved_books:
        st.info("The final DB is empty. Approve one or more books to populate it.")
        return

    st.caption(f"Approved books: {len(approved_books)}")

    approved_df = _approved_books_to_dataframe(approved_books)
    approved_excel = _to_excel_bytes(approved_df, "final_db")
    st.download_button(
        label="Download Final DB (Excel)",
        data=approved_excel,
        file_name="biblioforge_final_db.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    with st.expander("Show/Hide final DB list", expanded=False):
        for idx, book in enumerate(approved_books, start=1):
            title = book.normalized_title or book.raw_title or "Unknown title"
            author = book.author or "Unknown author"
            isbn = getattr(book, "isbn", None) or "-"
            year = getattr(book, "publication_year", None) or "-"
            rating = f"{book.average_rating:.2f}" if getattr(book, "average_rating", None) is not None else "-"
            tags = ", ".join((book.insights.tags if book.insights else [])[:6]) or "-"

            with st.expander(f"{idx}. {title} - {author}", expanded=False):
                st.markdown(f"**Title:** {title}")
                st.markdown(f"**Author:** {author}")
                st.markdown(f"**ISBN:** {isbn}")
                st.markdown(f"**Year:** {year}")
                st.markdown(f"**Rating:** {rating}")
                st.markdown(f"**Tags:** {tags}")


def main():
    process_pending_approval()
    if "auto_metadata_checked_ids" not in st.session_state:
        st.session_state["auto_metadata_checked_ids"] = []

    st.title("BiblioForge")
    st.caption("Workflow states: To Clean -> In Progress -> To Approve -> Approved")
    render_ingestion_box()
    render_excel_ingestion_box()

    summary_col, _ = st.columns([1, 3])
    summary_col.metric("Approved in final DB", len(controller.list_approved()))
    if summary_col.button("Clear approved DB", use_container_width=True):
        if hasattr(controller, "clear_approved"):
            removed = controller.clear_approved()
        else:
            removed = controller.approved_repository.clear_books()
        st.success(f"Cleared {removed} books from the approved DB.")
        st.rerun()

    render_final_db_list()

    if st.session_state.get("last_reject_message"):
        st.warning(st.session_state["last_reject_message"])
        st.session_state["last_reject_message"] = ""

    if st.session_state.get("last_approve_message"):
        st.success(st.session_state["last_approve_message"])
        st.session_state["last_approve_message"] = ""

    pending = controller.list_pending()
    if not pending:
        st.info("No books pending review. Add one above to start.")
        return

    st.markdown("Select a book to review")
    select_col, clear_col = st.columns([3, 1])
    pending_ids = [book.id for book in pending]
    if st.session_state.get("selected_book_id") not in pending_ids:
        st.session_state["selected_book_id"] = pending_ids[0]

    selected_id = select_col.selectbox(
        "Select a book to review",
        options=pending_ids,
        format_func=lambda bid: next(
            (normalize_title(b.raw_title or b.normalized_title, b.author) for b in pending if b.id == bid),
            bid,
        ),
        label_visibility="collapsed",
        key="selected_book_id",
    )
    with clear_col:
        if st.button("Clear queue", use_container_width=True):
            removed = controller.repository.clear_books()
            st.success(f"Cleared {removed} books from the review queue.")
            st.session_state["auto_metadata_checked_ids"] = []
            st.rerun()
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
        with st.spinner("Fetching initial metadata..."):
            refreshed = controller.ensure_review_metadata(book.id)
        if refreshed:
            book = refreshed
        checked_ids.add(book.id)
        st.session_state["auto_metadata_checked_ids"] = list(checked_ids)

    left, right = st.columns([1, 1])
    with left:
        render_context_column(book)
    with right:
        render_editing_column(book, pending_ids)


if __name__ == "__main__":
    main()
