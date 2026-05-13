"""Knowledge-source contracts for user and external clinical references.

The ingestion pipeline should not care whether chunks came from a pharmacist
upload, DailyMed, or a licensed reference provider. This module keeps that
boundary narrow: sources yield already-prepared chunks, and ingestion owns
embedding, persistence, status updates, and audit writes.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class KnowledgeSourceChunk:
    """A source chunk ready for embedding and persistence."""

    content: str
    tokens: int
    source_uri: str
    document_title: str | None = None
    section_title: str | None = None
    page_number: int | None = None
    row_number: int | None = None

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("knowledge source chunk content cannot be empty")
        if self.tokens <= 0:
            raise ValueError("knowledge source chunk tokens must be positive")
        if not self.source_uri.strip():
            raise ValueError("knowledge source chunk source_uri cannot be empty")


class KnowledgeSource(Protocol):
    """Produces chunks for one source document without persisting them."""

    async def list_chunks(self, document_id: UUID) -> AsyncIterator[KnowledgeSourceChunk]: ...
