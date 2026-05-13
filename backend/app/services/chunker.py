"""Token-aware chunking for knowledge-base segments.

This module intentionally keeps splitting local instead of routing all content
through a generic recursive text splitter. PharmaAide ingests more than prose:

- PDF text already carries document/page context.
- CSV rows must stay tied to their column headers.
- Future clinical documents may have section metadata that should travel with
  every chunk.

Because of that, the chunker works on already-shaped ``TextSegment`` inputs,
renders their context prefix, recursively tries clinical-friendly boundaries
for prose, counts tokens with ``tiktoken``, and keeps deterministic token
windows as the final fallback.

Why this base approach:

- token limits should be enforced on model-relevant tokens, not characters
  or words
- CSV and metadata-rich records need different behavior from prose
- deterministic fallback windows are easier to reason about for embeddings and
  retrieval

Text segments recursively try paragraph, line, and sentence-like boundaries
before falling back to token-window chunking with overlap. PDF page segments
enter the chunker as ``kind="text"``, so extracted page text gets the same
boundary-aware treatment.

CSV-row segments are handled separately: chunks are built from labeled lines so
column names stay attached to values. Oversized CSV fields repeat the field
label in each continuation chunk instead of emitting unlabeled fragments.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import structlog
import tiktoken

from app.services.kb_segments import TextSegment, render_segment

DEFAULT_MAX_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 50
TEXT_BOUNDARIES = ("\n\n", "\n", ". ", "; ", "? ", "! ")

log = structlog.get_logger(__name__)


class TokenEncoder(Protocol):
    def encode(self, text: str) -> list[int] | list[str]: ...

    def decode(self, tokens: list[int] | list[str]) -> str: ...


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    """A chunk ready for embedding and later persistence."""

    content: str
    tokens: int
    kind: str
    document_title: str | None
    section_title: str | None
    page_number: int | None
    row_number: int | None


def chunk_segments(
    segments: Sequence[TextSegment],
    *,
    encoder: TokenEncoder | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkDraft]:
    """Chunk cleaned segments while preserving source context in every chunk."""
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative")

    token_encoder = encoder or tiktoken.get_encoding("cl100k_base")
    chunks: list[ChunkDraft] = []
    for segment in segments:
        chunks.extend(
            _chunk_segment(
                segment,
                encoder=token_encoder,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            )
        )
    log.info(
        "kb_segments_chunked",
        segment_count=len(segments),
        chunk_count=len(chunks),
        chunk_kind_counts=_chunk_kind_counts(chunks),
        total_tokens=sum(chunk.tokens for chunk in chunks),
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
    return chunks


def _chunk_segment(
    segment: TextSegment,
    *,
    encoder: TokenEncoder,
    max_tokens: int,
    overlap_tokens: int,
) -> list[ChunkDraft]:
    rendered = render_segment(segment)
    prefix_text, body_text = _split_rendered_segment(segment, rendered)
    prefix_tokens = list(encoder.encode(prefix_text)) if prefix_text else []
    available_body_tokens = max_tokens - len(prefix_tokens)
    if available_body_tokens <= 0:
        raise ValueError("segment context exceeds max_tokens")
    if not body_text.strip():
        return []

    if segment.kind == "text":
        return _chunk_text_boundaries(
            segment,
            prefix_text=prefix_text,
            body_text=body_text,
            encoder=encoder,
            available_body_tokens=available_body_tokens,
            overlap_tokens=overlap_tokens,
        )

    if segment.kind == "csv_row":
        return _chunk_csv_row(
            segment,
            prefix_text=prefix_text,
            body_text=body_text,
            encoder=encoder,
            available_body_tokens=available_body_tokens,
        )

    return _chunk_body_tokens(
        segment,
        prefix_text=prefix_text,
        body_text=body_text,
        encoder=encoder,
        available_body_tokens=available_body_tokens,
        overlap_tokens=overlap_tokens if segment.kind == "text" else 0,
    )


def _split_rendered_segment(segment: TextSegment, rendered: str) -> tuple[str, str]:
    if not _has_context(segment):
        return "", rendered
    prefix, body = rendered.split("\n\n", maxsplit=1)
    return f"{prefix}\n\n", body


def _has_context(segment: TextSegment) -> bool:
    return any(
        value is not None
        for value in (
            segment.document_title,
            segment.section_title,
            segment.page_number,
            segment.row_number,
        )
    )


def _chunk_text_boundaries(
    segment: TextSegment,
    *,
    prefix_text: str,
    body_text: str,
    encoder: TokenEncoder,
    available_body_tokens: int,
    overlap_tokens: int,
) -> list[ChunkDraft]:
    return _chunk_by_boundaries(
        segment,
        prefix_text=prefix_text,
        body_text=body_text,
        encoder=encoder,
        available_body_tokens=available_body_tokens,
        overlap_tokens=overlap_tokens,
        boundaries=TEXT_BOUNDARIES,
    )


def _chunk_by_boundaries(
    segment: TextSegment,
    *,
    prefix_text: str,
    body_text: str,
    encoder: TokenEncoder,
    available_body_tokens: int,
    overlap_tokens: int,
    boundaries: Sequence[str],
) -> list[ChunkDraft]:
    body_text = body_text.strip()
    if len(list(encoder.encode(body_text))) <= available_body_tokens:
        return [_build_chunk(segment, prefix_text, body_text, encoder)]
    if not boundaries:
        return _chunk_body_tokens(
            segment,
            prefix_text=prefix_text,
            body_text=body_text,
            encoder=encoder,
            available_body_tokens=available_body_tokens,
            overlap_tokens=overlap_tokens,
        )

    boundary, *remaining_boundaries = boundaries
    blocks = _split_boundary_blocks(body_text, boundary)
    if len(blocks) <= 1:
        return _chunk_by_boundaries(
            segment,
            prefix_text=prefix_text,
            body_text=body_text,
            encoder=encoder,
            available_body_tokens=available_body_tokens,
            overlap_tokens=overlap_tokens,
            boundaries=remaining_boundaries,
        )

    return _pack_boundary_blocks(
        segment,
        prefix_text=prefix_text,
        blocks=blocks,
        joiner=_boundary_joiner(boundary),
        encoder=encoder,
        available_body_tokens=available_body_tokens,
        overlap_tokens=overlap_tokens,
        remaining_boundaries=remaining_boundaries,
    )


def _pack_boundary_blocks(
    segment: TextSegment,
    *,
    prefix_text: str,
    blocks: Sequence[str],
    joiner: str,
    encoder: TokenEncoder,
    available_body_tokens: int,
    overlap_tokens: int,
    remaining_boundaries: Sequence[str],
) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    current_blocks: list[str] = []
    current_tokens = 0
    separator_tokens = len(list(encoder.encode(joiner)))

    for block in blocks:
        block_token_count = len(list(encoder.encode(block)))
        if block_token_count > available_body_tokens:
            if current_blocks:
                chunks.append(
                    _build_chunk(segment, prefix_text, joiner.join(current_blocks), encoder)
                )
                current_blocks = []
                current_tokens = 0
            chunks.extend(
                _chunk_by_boundaries(
                    segment,
                    prefix_text=prefix_text,
                    body_text=block,
                    encoder=encoder,
                    available_body_tokens=available_body_tokens,
                    overlap_tokens=overlap_tokens,
                    boundaries=remaining_boundaries,
                )
            )
            continue

        candidate_tokens = block_token_count
        if current_blocks:
            candidate_tokens += current_tokens + separator_tokens
        if candidate_tokens > available_body_tokens:
            chunks.append(_build_chunk(segment, prefix_text, joiner.join(current_blocks), encoder))
            current_blocks = [block]
            current_tokens = block_token_count
            continue

        current_blocks.append(block)
        current_tokens = candidate_tokens

    if current_blocks:
        chunks.append(_build_chunk(segment, prefix_text, joiner.join(current_blocks), encoder))
    return chunks


def _chunk_csv_row(
    segment: TextSegment,
    *,
    prefix_text: str,
    body_text: str,
    encoder: TokenEncoder,
    available_body_tokens: int,
) -> list[ChunkDraft]:
    lines = [line.strip() for line in body_text.split("\n") if line.strip()]
    chunks: list[ChunkDraft] = []
    for line in lines:
        if len(list(encoder.encode(line))) <= available_body_tokens:
            chunks.append(_build_chunk(segment, prefix_text, line, encoder))
            continue
        chunks.extend(
            _chunk_oversized_csv_line(
                segment,
                prefix_text=prefix_text,
                line=line,
                encoder=encoder,
                available_body_tokens=available_body_tokens,
            )
        )
    return chunks


def _chunk_oversized_csv_line(
    segment: TextSegment,
    *,
    prefix_text: str,
    line: str,
    encoder: TokenEncoder,
    available_body_tokens: int,
) -> list[ChunkDraft]:
    label, separator, value = line.partition(":")
    if not separator:
        return _chunk_body_tokens(
            segment,
            prefix_text=prefix_text,
            body_text=line,
            encoder=encoder,
            available_body_tokens=available_body_tokens,
            overlap_tokens=0,
        )

    label_prefix = f"{label.strip()}: "
    label_tokens = list(encoder.encode(label_prefix))
    value_budget = available_body_tokens - len(label_tokens)
    if value_budget <= 0:
        return _chunk_body_tokens(
            segment,
            prefix_text=prefix_text,
            body_text=line,
            encoder=encoder,
            available_body_tokens=available_body_tokens,
            overlap_tokens=0,
        )

    value_tokens = list(encoder.encode(value.strip()))
    chunks: list[ChunkDraft] = []
    for start in range(0, len(value_tokens), value_budget):
        chunk_value = encoder.decode(value_tokens[start : start + value_budget]).strip()
        if chunk_value:
            chunks.append(
                _build_chunk(segment, prefix_text, f"{label_prefix}{chunk_value}", encoder)
            )
    return chunks


def _chunk_body_tokens(
    segment: TextSegment,
    *,
    prefix_text: str,
    body_text: str,
    encoder: TokenEncoder,
    available_body_tokens: int,
    overlap_tokens: int,
) -> list[ChunkDraft]:
    body_tokens = list(encoder.encode(body_text))
    if not body_tokens:
        return []

    step = available_body_tokens - overlap_tokens
    if step <= 0:
        raise ValueError("overlap_tokens must be smaller than the body token budget")

    chunks: list[ChunkDraft] = []
    for start in range(0, len(body_tokens), step):
        end = min(start + available_body_tokens, len(body_tokens))
        chunk_body = encoder.decode(body_tokens[start:end]).strip()
        if chunk_body:
            chunks.append(_build_chunk(segment, prefix_text, chunk_body, encoder))
        if end == len(body_tokens):
            break
    return chunks


def _split_boundary_blocks(text: str, boundary: str) -> list[str]:
    if boundary in ("\n\n", "\n"):
        return [block.strip() for block in text.split(boundary) if block.strip()]

    pattern = re.compile(rf"(?<={re.escape(boundary.strip())})\s+")
    return [block.strip() for block in pattern.split(text) if block.strip()]


def _boundary_joiner(boundary: str) -> str:
    if boundary in ("\n\n", "\n"):
        return boundary
    return " "


def _build_chunk(
    segment: TextSegment,
    prefix_text: str,
    body_text: str,
    encoder: TokenEncoder,
) -> ChunkDraft:
    chunk_text = f"{prefix_text}{body_text}" if prefix_text else body_text
    return ChunkDraft(
        content=chunk_text,
        tokens=len(list(encoder.encode(chunk_text))),
        kind=segment.kind,
        document_title=segment.document_title,
        section_title=segment.section_title,
        page_number=segment.page_number,
        row_number=segment.row_number,
    )


def _chunk_kind_counts(chunks: Sequence[ChunkDraft]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.kind] = counts.get(chunk.kind, 0) + 1
    return counts
