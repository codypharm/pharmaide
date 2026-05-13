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

Text and PDF segments use overlap because prose benefits from continuity across
windows. CSV-row segments do not overlap because the row labels already preserve
meaning and duplicated overlap would just repeat structured values.

If retrieval quality later shows that plain text or PDF chunks should respect
paragraph or section boundaries more closely, add a pre-splitting stage before
this module's token windowing rather than replacing the token-aware chunker.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import tiktoken

from app.services.kb_segments import TextSegment, render_segment

DEFAULT_MAX_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 50


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
    body_tokens = list(encoder.encode(body_text))
    available_body_tokens = max_tokens - len(prefix_tokens)
    if available_body_tokens <= 0:
        raise ValueError("segment context exceeds max_tokens")
    if not body_tokens:
        return []

    effective_overlap = overlap_tokens if segment.kind == "text" else 0
    step = available_body_tokens - effective_overlap
    if step <= 0:
        raise ValueError("overlap_tokens must be smaller than the body token budget")

    chunks: list[ChunkDraft] = []
    for start in range(0, len(body_tokens), step):
        end = min(start + available_body_tokens, len(body_tokens))
        chunk_body = encoder.decode(body_tokens[start:end]).strip()
        if not chunk_body:
            continue
        chunk_text = f"{prefix_text}{chunk_body}" if prefix_text else chunk_body
        chunks.append(
            ChunkDraft(
                content=chunk_text,
                tokens=len(list(encoder.encode(chunk_text))),
                kind=segment.kind,
                document_title=segment.document_title,
                section_title=segment.section_title,
                page_number=segment.page_number,
                row_number=segment.row_number,
            )
        )
        if end == len(body_tokens):
            break
    return chunks


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
