import time

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
    if book.ratings_count:
        metric_items.append(("Ratings Count", str(book.ratings_count)))
    if book.average_rating:
        metric_items.append(("Average Rating", f"{book.average_rating:.2f}"))
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
    if info_link:
        st.markdown(f"[Google Books Info]({info_link})")
    if preview_link:
        st.markdown(f"[Google Books Preview]({preview_link})")
    if canonical_volume_link:
        st.markdown(f"[Canonical Volume Page]({canonical_volume_link})")
    if reject_attempts:
        st.caption(f"Reject attempts: {reject_attempts}")

    ratio_val = book.positive_ratio if book.positive_ratio is not None else (
        (book.average_rating / 5) if book.average_rating is not None else None
    )
    if ratio_val is not None:
        ratio_pct = ratio_val * 100

        # Derive positive/negative counts either from total ratings or review samples.
        pos = neg = None
        if book.ratings_count:
            pos = int(round(ratio_val * book.ratings_count))
            neg = max(book.ratings_count - pos, 0)
        elif book.review_samples:
            sample_ratings = [s.rating for s in book.review_samples if isinstance(getattr(s, "rating", None), (int, float))]
            if sample_ratings:
                pos = sum(1 for r in sample_ratings if r >= 3.5)
                neg = sum(1 for r in sample_ratings if r < 3.5)

        sources = set()
        for sample in book.review_samples or []:
            name = (sample.reviewer or "").lower()
            if "goodreads" in name:
                sources.add("Goodreads")
            elif "amazon" in name:
                sources.add("Amazon")
            elif "google" in name:
                sources.add("Google Books")
            elif "rating signal" in name:
                sources.add("Rating Signal")
            elif "editorial" in name:
                sources.add("Editorial Extract")

        if ratio_val >= 0.75:
            color = "#1b8f3b"  # green
        elif ratio_val >= 0.5:
            color = "#c79a00"  # yellow
        else:
            color = "#c23b22"  # red

        ratio_html = f"<span style='color:{color}; font-size:30px; font-weight:800;'>{ratio_pct:.1f}%</span>"
        src_text = f"Sources: {', '.join(sorted(sources))}" if sources else ""

        parts = [ratio_html, "Positive Reviews"]
        if src_text:
            parts.append(src_text)
        st.markdown(" &nbsp; ".join(parts), unsafe_allow_html=True)

    if book.review_samples:
        st.markdown("### Review Samples")
        for sample in book.review_samples:
            st.markdown(f"- **{sample.reviewer}** ({sample.rating:.1f}/5): {sample.text}")

    st.markdown("### Rejected Information & Reasoning")
    if book.insights and book.insights.rejected_information:
        for note in book.insights.rejected_information:
            detail = note.detail or ""
            example = ""
            if "Removed example:" in detail:
                parts = detail.split("Removed example:", 1)
                detail = parts[0].strip()
                example = parts[1].strip().strip('"')

            st.markdown("<div class='rejected-item'>", unsafe_allow_html=True)
            st.markdown(f"**{note.reason}**")
            if detail:
                st.caption(detail)
            if example:
                st.markdown(
                    f"<div class='rejected-example'><strong>Removed example:</strong> <span style='text-decoration: line-through;'>{example}</span></div>",
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No rejected items recorded.")


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
        col_approve, col_reject = st.columns([1, 1])
        approve = col_approve.form_submit_button("Approve and Save", use_container_width=True)
        reject = col_reject.form_submit_button("Reject & Redo Search", use_container_width=True)

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

    trust_col, remove_col = st.columns([4, 1])
    remaining = len(pending_ids)
    trust_col.caption(f"Pending to approve: {remaining}")
    if trust_col.button("Trust the Process", help="Approve all pending books in one batch."):
        approved = controller.trust_process()
        st.success(f"Process trusted: {approved} books saved to the final DB in one batch.")

    if remove_col.button("Remove", help="Remove this book from the review queue."):
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
        st.caption("You can type only the title: the pipeline will try to resolve the author automatically.")

        fallback_catalog_code = ""
        if st.session_state.get("show_isbn_ean_fallback"):
            st.warning("Book not found. As a last resort, insert ISBN or EAN to resolve the exact edition.")
            fallback_catalog_code = st.text_input("ISBN or EAN (shown only after error)", value=default_catalog_code)

        submitted = st.form_submit_button("Find Matches")
        if submitted:
            candidates = controller.find_candidates(
                title,
                author or None,
                catalog_publisher=None,
                catalog_ean=fallback_catalog_code or None,
            )
            st.session_state["ingest_candidates"] = candidates
            st.session_state["ingest_input"] = {
                "title": title,
                "author": author,
                "catalog_ean": fallback_catalog_code,
            }
            if not candidates:
                try:
                    book = controller.ingest_raw_book(
                        title,
                        author or None,
                        catalog_ean=fallback_catalog_code or None,
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
                    st.session_state["last_failed_catalog_code"] = fallback_catalog_code
                    st.session_state["ingestion_error_message"] = str(exc)
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
                book = controller.ingest_raw_book(
                    sel_title or ingest_input.get("title"),
                    sel_author or None,
                    catalog_ean=ingest_input.get("catalog_ean") or None,
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
    default_path = "biblioforge/data/cleaned/books_cleaned.xlsx"
    excel_path_input = st.text_input("Excel path", value=default_path)
    resolved_path = controller.resolve_excel_path(excel_path_input)
    st.caption(f"Resolved import source: {resolved_path}")
    if not resolved_path.exists():
        st.warning("Excel path does not exist. Update the path before importing.")
    timer_placeholder = st.empty()
    if st.button("Load into review queue", use_container_width=True):
        start = time.perf_counter()
        timer_placeholder.info("⏱️ Import in corso...")
        try:
            total = controller.ingest_books_from_excel(excel_path_input)
            st.success(f"Imported {total} books into review queue.")
            if getattr(controller, "last_import_skipped", 0):
                st.warning(
                    f"Skipped {controller.last_import_skipped} rows because the book could not be resolved confidently."
                )
            timer_placeholder.success(f"⏱️ Import terminato in {format_duration(time.perf_counter() - start)}")
        except Exception as exc:
            timer_placeholder.error(
                f"⏱️ Import fallito dopo {format_duration(time.perf_counter() - start)}: {exc}"
            )
            st.error(f"Excel import failed: {exc}")


def main():
    process_pending_approval()

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
            st.rerun()
    book = next(b for b in pending if b.id == selected_id)

    left, right = st.columns([1, 1])
    with left:
        render_context_column(book)
    with right:
        render_editing_column(book, pending_ids)


if __name__ == "__main__":
    main()
