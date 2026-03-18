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
    maturity_rating = getattr(book, "maturity_rating", None)
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
            st.image(book.cover_url, width=160)
    with cols[1]:
        st.markdown(f"#### {book.normalized_title} - {book.author or 'Unknown Author'}")
        st.caption(book.raw_title)
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
    if maturity_rating:
        metric_items.append(("Maturity", maturity_rating))
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

    if book.positive_ratio is not None:
        ratio = f"{(book.positive_ratio or 0) * 100:.1f}%"
        st.markdown(f"## {ratio}\n% Positive Reviews")

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
                    f"<div class='rejected-example'><strong>Removed example:</strong> {example}</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No rejected items recorded.")


def render_editing_column(book: Book) -> None:
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
        col_approve, col_reject = st.columns([4, 1])
        approve = col_approve.form_submit_button("Approve and Save", use_container_width=True)
        reject = col_reject.form_submit_button("Reject", use_container_width=True)

        if approve:
            controller.approve_with_edits(book.id, summary, tags)
            st.success("Book approved and saved to the new final DB.")
        if reject:
            with st.spinner("Rejecting and regenerating..."):
                updated = controller.reject_and_retry(book.id)
            if updated:
                st.session_state["last_reject_message"] = "Book rejected and regenerated with a fresh crawl + AI pass."
                st.rerun()
            else:
                st.error("Reject failed: selected book was not found.")

    trust_col, remove_col = st.columns([4, 1])
    if trust_col.button("Trust the Process", help="Approve all pending books in one batch."):
        approved = controller.trust_process()
        st.success(f"Process trusted: {approved} books saved to the final DB in one batch.")

    if remove_col.button("x", help="Remove this book from the review queue."):
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
    with st.form("ingestion-form"):
        title = st.text_input("Raw Title", value="The Name of the Rose")
        author = st.text_input("Author (optional)", value="")
        st.caption("You can type only the title: the pipeline will try to resolve the author automatically.")
        submitted = st.form_submit_button("Ingest and Enrich")
        if submitted:
            try:
                book = controller.ingest_raw_book(title, author or None)
                st.success(f"Book queued for review: {book.normalized_title}")
            except BookNotFoundError as exc:
                st.error(str(exc))


def render_excel_ingestion_box() -> None:
    st.markdown("### Import from Excel")
    default_path = "biblioforge/data/cleaned/books_cleaned.xlsx"
    excel_path_input = st.text_input("Excel path", value=default_path)
    resolved_path = controller.resolve_excel_path(excel_path_input)
    st.caption(f"Resolved import source: {resolved_path}")
    if not resolved_path.exists():
        st.warning("Excel path does not exist. Update the path before importing.")
    if st.button("Load into review queue", use_container_width=True):
        try:
            total = controller.ingest_books_from_excel(excel_path_input)
            st.success(f"Imported {total} books into review queue.")
            if getattr(controller, "last_import_skipped", 0):
                st.warning(
                    f"Skipped {controller.last_import_skipped} rows because the book could not be resolved confidently."
                )
        except Exception as exc:
            st.error(f"Excel import failed: {exc}")


def main():
    st.title("BiblioForge")
    st.caption("Workflow states: To Clean -> In Progress -> To Approve -> Approved")
    render_ingestion_box()
    render_excel_ingestion_box()

    top_right = st.columns([1, 1])[1]
    top_right.metric("Approved in final DB", len(controller.list_approved()))

    if st.session_state.get("last_reject_message"):
        st.warning(st.session_state["last_reject_message"])
        st.session_state["last_reject_message"] = ""

    pending = controller.list_pending()
    if not pending:
        st.info("No books pending review. Add one above to start.")
        return

    selected_id = st.selectbox(
        "Select a book to review",
        options=[book.id for book in pending],
        format_func=lambda bid: next(
            (normalize_title(b.raw_title or b.normalized_title, b.author) for b in pending if b.id == bid),
            bid,
        ),
    )
    book = next(b for b in pending if b.id == selected_id)

    left, right = st.columns([1, 1])
    with left:
        render_context_column(book)
    with right:
        render_editing_column(book)


if __name__ == "__main__":
    main()
