"""Plain-text knowledge-base parser."""

from app.services.kb_segments import TextSegment, clean_text


def parse_text_segments(data: bytes, *, title: str | None = None) -> list[TextSegment]:
    """Decode a UTF-8 text upload into one cleaned source segment."""
    text = data.decode("utf-8-sig")
    content = clean_text(text)
    if not content:
        return []
    return [
        TextSegment(
            kind="text",
            content=content,
            document_title=clean_text(title) if title else None,
        )
    ]
