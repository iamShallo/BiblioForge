import streamlit as st

from biblioforge.controllers.pipeline_controller import PipelineController
from biblioforge.models.book import Book, BookStatus


controller = PipelineController()
st.set_page_config(page_title="BiblioForge", layout="wide")


def render_context_column(book: Book) -> None:
    st.markdown("### Context & Extracted Data")
    cols = st.columns([1, 2])
    with cols[0]:
        if book.cover_url:
            st.image(book.cover_url, width=160)
    with cols[1]:
        st.markdown(f"#### {book.normalized_title} - {book.author or 'Unknown Author'}")
        st.caption(book.raw_title)
        st.button("AI_PROCESSED", disabled=True, use_container_width=False)

    st.markdown("---")
    meta_cols = st.columns(3)
    meta_cols[0].metric("Original Year", book.publication_year or "-" )
    meta_cols[1].metric("Pages", book.pages or "-")
    meta_cols[2].metric("ISBN", book.isbn or "-")

    st.markdown("---")
    ratio = f"{(book.positive_ratio or 0) * 100:.1f}%" if book.positive_ratio is not None else "-"
    st.markdown(f"## {ratio}\n% Positive Reviews")

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

    with st.form(key="editing-form"):
        summary = st.text_area("Summary", value=book.insights.summary, height=180)
        tags = st.multiselect(
            "Tags",
            options=sorted(set(book.insights.tags + ["Historical Fiction", "Mystery", "Philosophy", "Theology", "Investigation"])),
            default=book.insights.tags,
        )
        col1, col2 = st.columns([1, 1])
        reject = col1.form_submit_button("Reject & Redo Search")
        approve = col2.form_submit_button("Approve and Save")

        if approve:
            book.insights.summary = summary
            book.insights.tags = tags
            controller.approve(book.id)
            st.success("Book approved and saved.")
        if reject:
            controller.reject_and_retry(book.id)
            st.warning("Marked for rerun. You can re-launch ingestion from main pipeline.")


def render_ingestion_box():
    st.markdown("### Add a Book")
    with st.form("ingestion-form"):
        title = st.text_input("Raw Title", value="The Name of the Rose - Umberto Eco")
        author = st.text_input("Author", value="Umberto Eco")
        submitted = st.form_submit_button("Ingest and Enrich")
        if submitted:
            book = controller.ingest_raw_book(title, author)
            st.success(f"Book queued for review: {book.normalized_title}")


def main():
    st.title("BiblioForge")
    render_ingestion_box()

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
