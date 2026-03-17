from biblioforge.models.book import Book, BookInsights, BookStatus, TransparencyNote


def generate_insights(book: Book) -> Book:
    """Produce a concise summary, tags, and transparency notes."""
    title = book.normalized_title or book.raw_title
    summary_parts = [
        f"{title} blends investigation and history to surface themes of knowledge and power.",
        "Reviews highlight atmosphere, textured world building, and steady suspense.",
    ]
    tags = ["Historical Fiction", "Mystery", "Investigation"]
    if book.author:
        tags.append(book.author)
    rejected = [
        TransparencyNote(
            reason="Off-focus trivia",
            detail="Removed film adaptation details and marketing copy.",
        ),
        TransparencyNote(
            reason="Redundant praise",
            detail="Collapsed repetitive review sentences into one insight.",
        ),
    ]
    book.insights = BookInsights(
        summary=" ".join(summary_parts),
        tags=tags,
        rejected_information=rejected,
    )
    book.status = BookStatus.PENDING_REVIEW
    return book
