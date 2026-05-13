"""Plain-text knowledge-base parser."""

import structlog

from app.services.kb_segments import TextSegment, clean_text

log = structlog.get_logger(__name__)


def parse_text_segments(data: bytes, *, title: str | None = None) -> list[TextSegment]:
    """Decode a UTF-8 text upload into one cleaned source segment."""
    text = data.decode("utf-8-sig")
    content = clean_text(text)
    if not content:
        log.info(
            "kb_text_parsed",
            segment_count=0,
            title_present=title is not None,
            byte_count=len(data),
        )
        return []
    segments = [
        TextSegment(
            kind="text",
            content=content,
            document_title=clean_text(title) if title else None,
        )
    ]
    log.info(
        "kb_text_parsed",
        segment_count=1,
        title_present=title is not None,
        byte_count=len(data),
    )
    return segments
