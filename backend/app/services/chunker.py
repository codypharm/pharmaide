"""Token-aware chunking for knowledge-base segments.

This module intentionally does not use a generic recursive text splitter as the
primary strategy. PharmaAide ingests more than prose:

- PDF text already carries document/page context.
- CSV rows must stay tied to their column headers.
- Future clinical documents may have section metadata that should travel with
  every chunk.

Because of that, the chunker works on already-shaped ``TextSegment`` inputs,
renders their context prefix, counts tokens with ``tiktoken``, and applies a
deterministic token window.

Why this base approach:

- token limits should be enforced on model-relevant tokens, not characters
  or words
- CSV and metadata-rich records need different behavior from prose
- fixed token windows are easier to reason about for embeddings and retrieval

Text segments now try paragraph-preserving pre-splitting first. When paragraph
blocks fit inside the token budget, they are emitted intact. Only oversized
blocks fall back to token-window chunking with overlap. PDF page segments and
CSV-row segments still go straight to deterministic token windowing.

Text and PDF token windows use overlap because prose benefits from continuity
across windows. CSV-row segments do not overlap because the row labels already
preserve meaning and duplicated overlap would just repeat structured values.

Text segments already use paragraph-preserving pre-splitting before token
windowing. PDF segments still use direct token windowing today; if retrieval
quality shows page text should respect paragraph or section boundaries more
closely, add the same pre-splitting stage for PDF segments rather than
replacing the token-aware chunker.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import structlog
import tiktoken

from app.services.kb_segments import TextSegment, render_segment

DEFAULT_MAX_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 50

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

    # Plain text benefits from respecting paragraph boundaries where possible.
    # Structured row segments skip this path and go straight to token windows.
    if segment.kind == "text":
        paragraph_chunks = _chunk_text_paragraphs(
            segment,
            prefix_text=prefix_text,
            body_text=body_text,
            encoder=encoder,
            available_body_tokens=available_body_tokens,
            overlap_tokens=overlap_tokens,
        )
        if paragraph_chunks is not None:
            return paragraph_chunks

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


def _chunk_text_paragraphs(
    segment: TextSegment,
    *,
    prefix_text: str,
    body_text: str,
    encoder: TokenEncoder,
    available_body_tokens: int,
    overlap_tokens: int,
) -> list[ChunkDraft] | None:
    paragraphs = [paragraph.strip() for paragraph in body_text.split("\n\n") if paragraph.strip()]
    if len(paragraphs) <= 1:
        return None

    chunks: list[ChunkDraft] = []
    current_paragraphs: list[str] = []
    current_tokens = 0
    separator_tokens = len(list(encoder.encode("\n\n")))

    for paragraph in paragraphs:
        paragraph_token_count = len(list(encoder.encode(paragraph)))
        if paragraph_token_count > available_body_tokens:
            if current_paragraphs:
                chunks.append(
                    _build_chunk(
                        segment,
                        prefix_text,
                        "\n\n".join(current_paragraphs),
                        encoder,
                    )
                )
                current_paragraphs = []
                current_tokens = 0
            chunks.extend(
                _chunk_body_tokens(
                    segment,
                    prefix_text=prefix_text,
                    body_text=paragraph,
                    encoder=encoder,
                    available_body_tokens=available_body_tokens,
                    overlap_tokens=overlap_tokens,
                )
            )
            continue

        candidate_tokens = paragraph_token_count
        if current_paragraphs:
            candidate_tokens += current_tokens + separator_tokens
        if candidate_tokens > available_body_tokens:
            chunks.append(
                _build_chunk(
                    segment,
                    prefix_text,
                    "\n\n".join(current_paragraphs),
                    encoder,
                )
            )
            current_paragraphs = [paragraph]
            current_tokens = paragraph_token_count
            continue

        current_paragraphs.append(paragraph)
        current_tokens = candidate_tokens

    if current_paragraphs:
        chunks.append(_build_chunk(segment, prefix_text, "\n\n".join(current_paragraphs), encoder))
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
