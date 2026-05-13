"""Cache DailyMed label chunks into the existing knowledge-base tables.

The hybrid DailyMed design fetches labels on first need, stores selected
sections as normal KB chunks, and lets the existing retrieval service cite
them on later analyses. This module owns the durable cache step; it does not
call DailyMed directly.
"""

from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.knowledge_sources import KnowledgeSource, KnowledgeSourceChunk
from app.db.models import AuditLogEntry, KnowledgeChunk, KnowledgeDocument
from app.services.kb_ingestion import EmbeddingVector, vector_literal

Embedder = Callable[[Sequence[str]], Awaitable[list[EmbeddingVector]]]

log = structlog.get_logger(__name__)


async def ensure_dailymed_cached(
    session: AsyncSession,
    *,
    kb_scope_id: UUID,
    source: KnowledgeSource,
    source_uri: str,
    title: str,
    embedder: Embedder,
) -> KnowledgeDocument:
    """Create a ready DailyMed KB document if this scoped label is not cached."""
    cached = await _cached_document(session, kb_scope_id=kb_scope_id, source_uri=source_uri)
    if cached is not None:
        log.info("dailymed_cache_hit", document_id=str(cached.id), source_uri=source_uri)
        return cached

    document = KnowledgeDocument(
        source_type="dailymed",
        source_uri=source_uri,
        title=title,
        mime="application/spl+xml",
        status="ingesting",
        uploaded_by=kb_scope_id,
    )
    session.add(document)
    await session.flush()

    try:
        source_chunks = [chunk async for chunk in source.list_chunks(document.id)]
        embeddings = await embedder([chunk.content for chunk in source_chunks])
        _validate_embedding_count(source_chunks, embeddings)
        _persist_chunks(
            session,
            document=document,
            source_chunks=source_chunks,
            embeddings=embeddings,
        )
    except Exception:
        document.status = "failed"
        document.error_text = "dailymed_ingestion_failed"
        session.add(
            AuditLogEntry(
                event_type="kb_doc_ingestion_failed",
                resource_type="kb_document",
                resource_id=document.id,
                payload={
                    "document_id": str(document.id),
                    "source_type": "dailymed",
                    "error": "dailymed_ingestion_failed",
                },
            )
        )
        log.exception("dailymed_cache_failed", document_id=str(document.id), source_uri=source_uri)
        raise

    document.status = "ready"
    document.error_text = None
    tokens_total = sum(chunk.tokens for chunk in source_chunks)
    session.add(
        AuditLogEntry(
            event_type="kb_doc_ingested",
            resource_type="kb_document",
            resource_id=document.id,
            payload={
                "document_id": str(document.id),
                "source_type": "dailymed",
                "chunk_count": len(source_chunks),
                "tokens_total": tokens_total,
            },
        )
    )
    log.info(
        "dailymed_cache_created",
        document_id=str(document.id),
        source_uri=source_uri,
        chunk_count=len(source_chunks),
        tokens_total=tokens_total,
    )
    await session.flush()
    return document


async def _cached_document(
    session: AsyncSession,
    *,
    kb_scope_id: UUID,
    source_uri: str,
) -> KnowledgeDocument | None:
    result = await session.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.source_type == "dailymed",
            KnowledgeDocument.source_uri == source_uri,
            KnowledgeDocument.uploaded_by == kb_scope_id,
            KnowledgeDocument.status == "ready",
        )
    )
    return result.scalar_one_or_none()


def _validate_embedding_count(
    source_chunks: Sequence[KnowledgeSourceChunk],
    embeddings: Sequence[EmbeddingVector],
) -> None:
    if len(source_chunks) != len(embeddings):
        raise ValueError("embedding count does not match DailyMed chunk count")


def _persist_chunks(
    session: AsyncSession,
    *,
    document: KnowledgeDocument,
    source_chunks: Sequence[KnowledgeSourceChunk],
    embeddings: Sequence[EmbeddingVector],
) -> None:
    for ordinal, (chunk, embedding) in enumerate(zip(source_chunks, embeddings, strict=True)):
        session.add(
            KnowledgeChunk(
                document_id=document.id,
                ordinal=ordinal,
                content=chunk.content,
                embedding=vector_literal(embedding),
                tokens=chunk.tokens,
            )
        )
