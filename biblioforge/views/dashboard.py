import streamlit as st
from pathlib import Path

from biblioforge.controllers.pipeline_controller import PipelineController
from biblioforge.models.book import Book, BookStatus


controller = PipelineController()
st.set_page_config(page_title="BiblioForge", layout="wide")


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
        metric_items.append(("Publisher", book.publisher))
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
            target.markdown(f"**{label}:** {value}")

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

    st.markdown("---")
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
            st.markdown(f"- **{note.reason}:** {note.detail}")
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

    if st.button("Trust the Process", help="Approve all pending books in one batch."):
        approved = controller.trust_process()
        st.success(f"Process trusted: {approved} books saved to the final DB in one batch.")


def render_ingestion_box():
    st.markdown("### Add a Book")
    with st.form("ingestion-form"):
        title = st.text_input("Raw Title", value="The Name of the Rose - Umberto Eco")
        author = st.text_input("Author", value="Umberto Eco")
        submitted = st.form_submit_button("Ingest and Enrich")
        if submitted:
            book = controller.ingest_raw_book(title, author)
            st.success(f"Book queued for review: {book.normalized_title}")


def render_excel_ingestion_box() -> None:
    st.markdown("### Import from Excel")
    default_path = Path(__file__).resolve().parents[2] / "data" / "cleaned" / "books_cleaned.xlsx"
    with st.form("excel-ingestion-form"):
        excel_path = st.text_input("Clean Excel path", value=str(default_path))
        title_column = st.text_input("Title column", value="Title")
        author_column = st.text_input("Author column", value="Author")
        submitted = st.form_submit_button("Load into review queue")
        if submitted:
            try:
                queued = controller.ingest_books_from_excel(Path(excel_path), title_column, author_column)
                st.success(f"Import completed: {queued} books loaded into review.")
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
        format_func=lambda bid: next((b.normalized_title for b in pending if b.id == bid), bid),
    )
    book = next(b for b in pending if b.id == selected_id)

    left, right = st.columns([1, 1])
    with left:
        render_context_column(book)
    with right:
        render_editing_column(book)


if __name__ == "__main__":
    main()
