"""CSV knowledge-base parser."""

import csv
from io import StringIO

from app.services.kb_segments import TextSegment, clean_text, csv_row_to_segment


def parse_csv_segments(data: bytes, *, title: str | None = None) -> list[TextSegment]:
    """Parse a CSV upload into row-level labeled source segments."""
    text = data.decode("utf-8-sig")
    reader = csv.reader(StringIO(text))
    try:
        headers = next(reader)
    except StopIteration:
        return []

    document_title = clean_text(title) if title else None
    segments: list[TextSegment] = []
    for row_number, row in enumerate(reader, start=2):
        segment = csv_row_to_segment(
            headers,
            row,
            document_title=document_title,
            row_number=row_number,
        )
        if segment.content:
            segments.append(segment)
    return segments
