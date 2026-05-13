"""Knowledge-base text normalization and segment shaping.

The ingestion pipeline should chunk already-shaped segments, not raw parser
output. That keeps clinically useful context like document title, section, page,
and CSV column labels attached before embeddings are generated.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

SegmentKind = Literal["text", "csv_row"]

_INLINE_WHITESPACE_RE = re.compile(r"[ \t]+")


@dataclass(frozen=True, slots=True)
class TextSegment:
    """Cleaned text plus the source context that should travel with a chunk."""

    kind: SegmentKind
    content: str
    document_title: str | None = None
    section_title: str | None = None
    page_number: int | None = None
    row_number: int | None = None


def clean_text(text: str) -> str:
    """Normalize parser output without rewriting clinical content."""
    normalized = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    previous_blank = False

    for raw_line in normalized.split("\n"):
        line = _clean_line(raw_line)
        is_blank = line == ""
        if is_blank and previous_blank:
            continue
        lines.append(line)
        previous_blank = is_blank

    return "\n".join(lines).strip()


def csv_row_to_segment(
    headers: Sequence[str],
    row: Sequence[str],
    *,
    document_title: str | None = None,
    row_number: int | None = None,
) -> TextSegment:
    """Convert one CSV row into a self-contained labeled clinical record."""
    lines: list[str] = []
    for index, value in enumerate(row):
        cleaned_value = clean_text(value)
        if not cleaned_value:
            continue
        lines.append(f"{_header_label(headers, index)}: {cleaned_value}")

    return TextSegment(
        kind="csv_row",
        content="\n".join(lines),
        document_title=clean_text(document_title) if document_title else None,
        row_number=row_number,
    )


def render_segment(segment: TextSegment) -> str:
    """Render source context and content into the text later embedded."""
    prefix = _context_lines(segment)
    content = clean_text(segment.content)
    if not prefix:
        return content
    return "\n".join([*prefix, "", content])


def _clean_line(line: str) -> str:
    printable = "".join(
        char for char in line if char == "\t" or not unicodedata.category(char).startswith("C")
    )
    return _INLINE_WHITESPACE_RE.sub(" ", printable).strip()


def _header_label(headers: Sequence[str], index: int) -> str:
    if index >= len(headers):
        return f"column_{index + 1}"
    header = clean_text(headers[index])
    return header or f"column_{index + 1}"


def _context_lines(segment: TextSegment) -> list[str]:
    lines: list[str] = []
    if segment.document_title:
        lines.append(f"Document: {clean_text(segment.document_title)}")
    if segment.section_title:
        lines.append(f"Section: {clean_text(segment.section_title)}")
    if segment.page_number is not None:
        lines.append(f"Page: {segment.page_number}")
    if segment.row_number is not None:
        lines.append(f"Row: {segment.row_number}")
    return lines
