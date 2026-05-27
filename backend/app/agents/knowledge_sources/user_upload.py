"""Knowledge source for pharmacist-uploaded local files.

The API stores upload bytes outside Postgres and persists only document
metadata. This source is the adapter that turns those local bytes back into
chunkable text for the shared ingestion service.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.agents.knowledge_sources import KnowledgeSourceChunk
from app.services.chunker import ChunkDraft, chunk_segments
from app.services.kb_parsers.csv import parse_csv_segments
from app.services.kb_parsers.pdf import parse_pdf_segments
from app.services.kb_parsers.text import parse_text_segments
from app.services.kb_segments import TextSegment


@dataclass(frozen=True, slots=True)
class UserUploadSource:
    """Read a stored user upload and yield chunks for embedding."""

    path: Path
    mime: str
    title: str
    source_uri: str

    async def list_chunks(self, _document_id: UUID) -> AsyncIterator[KnowledgeSourceChunk]:
        for chunk in _chunks_from_bytes(
            self.path.read_bytes(),
            mime=self.mime,
            title=self.title,
            source_uri=self.source_uri,
        ):
            yield chunk


@dataclass(frozen=True, slots=True)
class UserUploadBytesSource:
    """Read already-loaded upload bytes and yield chunks for embedding."""

    data: bytes
    mime: str
    title: str
    source_uri: str

    async def list_chunks(self, _document_id: UUID) -> AsyncIterator[KnowledgeSourceChunk]:
        for chunk in _chunks_from_bytes(
            self.data,
            mime=self.mime,
            title=self.title,
            source_uri=self.source_uri,
        ):
            yield chunk


def _chunks_from_bytes(
    data: bytes,
    *,
    mime: str,
    title: str,
    source_uri: str,
) -> list[KnowledgeSourceChunk]:
    segments = _parse_segments(data, mime=mime, title=title)
    return [_source_chunk(chunk, source_uri=source_uri) for chunk in chunk_segments(segments)]


def _parse_segments(data: bytes, *, mime: str, title: str) -> list[TextSegment]:
    if mime == "application/pdf":
        return parse_pdf_segments(data, title=title)
    if mime in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        return parse_csv_segments(data, title=title)
    return parse_text_segments(data, title=title)


def _source_chunk(chunk: ChunkDraft, *, source_uri: str) -> KnowledgeSourceChunk:
    return KnowledgeSourceChunk(
        content=chunk.content,
        tokens=chunk.tokens,
        source_uri=source_uri,
        document_title=chunk.document_title,
        section_title=chunk.section_title,
        page_number=chunk.page_number,
        row_number=chunk.row_number,
    )
