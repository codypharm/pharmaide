"""PDF knowledge-base parser."""

from typing import Any

import pypdfium2 as pdfium
import structlog

from app.services.kb_segments import TextSegment, clean_text

log = structlog.get_logger(__name__)


def parse_pdf_segments(data: bytes, *, title: str | None = None) -> list[TextSegment]:
    """Parse a PDF upload into one cleaned segment per non-empty page."""
    document = pdfium.PdfDocument(data)
    document_title = clean_text(title) if title else None
    segments: list[TextSegment] = []
    page_count = len(document)

    try:
        for page_index in range(page_count):
            page = document[page_index]
            try:
                text_page = page.get_textpage()
                try:
                    content = clean_text(text_page.get_text_range())
                finally:
                    _close_if_present(text_page)
            finally:
                _close_if_present(page)

            if not content:
                continue

            segments.append(
                TextSegment(
                    kind="text",
                    content=content,
                    document_title=document_title,
                    page_number=page_index + 1,
                )
            )
    finally:
        _close_if_present(document)

    log.info(
        "kb_pdf_parsed",
        page_count=page_count,
        segment_count=len(segments),
        title_present=title is not None,
        non_empty_pages=[
            segment.page_number for segment in segments if segment.page_number is not None
        ],
    )
    return segments


def _close_if_present(resource: Any) -> None:
    close = getattr(resource, "close", None)
    if callable(close):
        close()
