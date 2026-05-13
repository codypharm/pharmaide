"""CSV knowledge-base parser."""

import csv
from io import StringIO

import structlog

from app.services.kb_segments import TextSegment, clean_text, csv_row_to_segment

log = structlog.get_logger(__name__)


def parse_csv_segments(data: bytes, *, title: str | None = None) -> list[TextSegment]:
    """Parse a CSV upload into row-level labeled source segments."""
    text = data.decode("utf-8-sig")
    reader = csv.reader(StringIO(text))
    try:
        headers = next(reader)
    except StopIteration:
        log.info("kb_csv_parsed", row_count=0, segment_count=0, title_present=title is not None)
        return []

    document_title = clean_text(title) if title else None
    segments: list[TextSegment] = []
    data_row_count = 0
    # The first CSV row is treated as the schema for every later row so
    # retrieved chunks keep field meaning even when seen in isolation.
    for row_number, row in enumerate(reader, start=2):
        data_row_count += 1
        segment = csv_row_to_segment(
            headers,
            row,
            document_title=document_title,
            row_number=row_number,
        )
        if segment.content:
            segments.append(segment)
    log.info(
        "kb_csv_parsed",
        header_count=len(headers),
        row_count=data_row_count,
        segment_count=len(segments),
        title_present=title is not None,
    )
    return segments
