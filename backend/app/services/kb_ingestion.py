"""Knowledge-base ingestion core.

This service owns the durable part of ingestion: source chunks become embedded
database rows, document status advances, and non-PHI audit events are written.
Upload storage remains outside this module; callers inject a ``KnowledgeSource``
so local files, blob storage, and future external sources can share the same
persistence path.
"""

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.knowledge_sources import KnowledgeSource, KnowledgeSourceChunk
from app.db.models import AuditLogEntry, KnowledgeChunk, KnowledgeDocument

EmbeddingVector = list[float]
Embedder = Callable[[Sequence[str]], Awaitable[list[EmbeddingVector]]]

log = structlog.get_logger(__name__)


async def ingest_document(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
    *,
    source: KnowledgeSource,
    embedder: Embedder,
) -> None:
    """Ingest one knowledge document from an injected source."""
    started_at = datetime.now(UTC)
    try:
        source_chunks = await _collect_source_chunks(source, document_id)
        embeddings = await embedder([chunk.content for chunk in source_chunks])
        _validate_embedding_count(source_chunks, embeddings)
        await _mark_ingested(
            session_factory,
            document_id,
            source_chunks=source_chunks,
            embeddings=embeddings,
            duration_ms=_duration_ms(started_at),
        )
    except Exception:
        log.exception("kb_doc_ingestion_error", document_id=str(document_id))
        await _mark_failed(session_factory, document_id, duration_ms=_duration_ms(started_at))


async def _collect_source_chunks(
    source: KnowledgeSource,
    document_id: UUID,
) -> list[KnowledgeSourceChunk]:
    chunks = [chunk async for chunk in source.list_chunks(document_id)]
    log.info(
        "kb_doc_chunks_collected",
        document_id=str(document_id),
        chunk_count=len(chunks),
        tokens_total=sum(chunk.tokens for chunk in chunks),
    )
    return chunks


def _validate_embedding_count(
    source_chunks: Sequence[KnowledgeSourceChunk],
    embeddings: Sequence[EmbeddingVector],
) -> None:
    if len(source_chunks) != len(embeddings):
        raise ValueError("embedding count does not match chunk count")


async def _mark_ingested(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
    *,
    source_chunks: Sequence[KnowledgeSourceChunk],
    embeddings: Sequence[EmbeddingVector],
    duration_ms: int,
) -> None:
    async with session_factory() as session, session.begin():
        document = await _get_document_for_update(session, document_id)
        if document is None:
            log.info("kb_doc_ingestion_skipped", document_id=str(document_id), reason="not_found")
            return
        if _is_removed(document):
            log.info("kb_doc_ingestion_skipped", document_id=str(document_id), reason="removed")
            return

        await session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
        )
        for ordinal, (chunk, embedding) in enumerate(zip(source_chunks, embeddings, strict=True)):
            session.add(
                KnowledgeChunk(
                    document_id=document_id,
                    ordinal=ordinal,
                    content=chunk.content,
                    embedding=_vector_literal(embedding),
                    tokens=chunk.tokens,
                )
            )

        document.status = "ready"
        document.error_text = None
        document.updated_at = func.clock_timestamp()
        tokens_total = sum(chunk.tokens for chunk in source_chunks)
        session.add(
            AuditLogEntry(
                event_type="kb_doc_ingested",
                resource_type="kb_document",
                resource_id=document_id,
                payload={
                    "document_id": str(document_id),
                    "chunk_count": len(source_chunks),
                    "tokens_total": tokens_total,
                },
            )
        )
        log.info(
            "kb_doc_ingested",
            document_id=str(document_id),
            chunk_count=len(source_chunks),
            tokens_total=tokens_total,
            duration_ms=duration_ms,
        )


async def _mark_failed(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
    *,
    duration_ms: int,
) -> None:
    async with session_factory() as session, session.begin():
        document = await _get_document_for_update(session, document_id)
        if document is None:
            log.info(
                "kb_doc_ingestion_failed_skipped",
                document_id=str(document_id),
                reason="not_found",
            )
            return
        if _is_removed(document):
            log.info(
                "kb_doc_ingestion_failed_skipped",
                document_id=str(document_id),
                reason="removed",
            )
            return

        document.status = "failed"
        document.error_text = "ingestion_failed"
        document.updated_at = func.clock_timestamp()
        session.add(
            AuditLogEntry(
                event_type="kb_doc_ingestion_failed",
                resource_type="kb_document",
                resource_id=document_id,
                payload={
                    "document_id": str(document_id),
                    "error": "ingestion_failed",
                },
            )
        )
        log.warning(
            "kb_doc_ingestion_failed",
            document_id=str(document_id),
            duration_ms=duration_ms,
            error="ingestion_failed",
        )


async def _get_document_for_update(
    session: AsyncSession,
    document_id: UUID,
) -> KnowledgeDocument | None:
    result = await session.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document_id).with_for_update()
    )
    return result.scalar_one_or_none()


def _vector_literal(embedding: Sequence[float]) -> str:
    """Render a pgvector literal; never log the vector contents."""
    return f"[{','.join(str(value) for value in embedding)}]"


def _is_removed(document: KnowledgeDocument) -> bool:
    """Removed documents are terminal even if an older ingestion task finishes later."""
    return document.status == "removed"


def _duration_ms(started_at: datetime) -> int:
    return round((datetime.now(UTC) - started_at).total_seconds() * 1000)
