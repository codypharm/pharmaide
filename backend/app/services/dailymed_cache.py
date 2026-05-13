"""Cache DailyMed label chunks into the existing knowledge-base tables.

The hybrid DailyMed design fetches labels on first need, stores selected
sections as normal KB chunks, and lets the existing retrieval service cite
them on later analyses. This module owns the durable cache step; it does not
call DailyMed directly.
"""

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analysis_schemas import MedicationGrounding
from app.agents.knowledge_sources import KnowledgeSource, KnowledgeSourceChunk
from app.agents.knowledge_sources.dailymed import DailyMedClient, DailyMedSource
from app.db.models import AuditLogEntry, KnowledgeChunk, KnowledgeDocument
from app.services.kb_ingestion import EmbeddingVector, vector_literal
from app.services.kb_scope import GLOBAL_DAILYMED_SCOPE_ID

Embedder = Callable[[Sequence[str]], Awaitable[list[EmbeddingVector]]]
DAILYMED_CACHE_MAX_AGE_DAYS = 90

log = structlog.get_logger(__name__)


async def ensure_dailymed_cached(
    session: AsyncSession,
    *,
    source: KnowledgeSource,
    source_uri: str,
    title: str,
    embedder: Embedder,
    max_age_days: int = DAILYMED_CACHE_MAX_AGE_DAYS,
) -> KnowledgeDocument:
    """Create a ready global DailyMed KB document if this label is not cached."""
    cached = await _cached_document(session, source_uri=source_uri)
    if cached is not None:
        if _cache_is_stale(cached.updated_at, max_age_days=max_age_days):
            return await _refresh_cached_document(
                session,
                document=cached,
                source=source,
                source_uri=source_uri,
                embedder=embedder,
            )
        log.info("dailymed_cache_hit", document_id=str(cached.id), source_uri=source_uri)
        return cached

    document = KnowledgeDocument(
        source_type="dailymed",
        source_uri=source_uri,
        title=title,
        mime="application/spl+xml",
        status="ingesting",
        uploaded_by=GLOBAL_DAILYMED_SCOPE_ID,
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


async def ensure_dailymed_cached_for_groundings(
    session: AsyncSession,
    *,
    groundings: Sequence[MedicationGrounding],
    client: DailyMedClient,
    embedder: Embedder,
    max_age_days: int = DAILYMED_CACHE_MAX_AGE_DAYS,
) -> int:
    """Cache DailyMed labels for grounded drugs before KB retrieval runs.

    DailyMed is best-effort evidence, not a blocker. A failed lookup for one
    drug should not prevent retrieval from pharmacist-uploaded clinical assets.
    """
    cached_count = 0
    requested_count = 0
    seen_rxcuis: set[str] = set()
    for grounding in groundings:
        rxcui = grounding.rxcui.strip() if grounding.rxcui else ""
        if not rxcui or rxcui in seen_rxcuis:
            continue
        seen_rxcuis.add(rxcui)

        requested_count += 1
        drug_name = grounding.normalized_name or grounding.medication_name
        try:
            label = await client.find_label(rxcui=rxcui, drug_name=drug_name)
            if label is None:
                continue

            await ensure_dailymed_cached(
                session,
                source=DailyMedSource(
                    client=client,
                    rxcui=rxcui,
                    drug_name=drug_name,
                    label=label,
                ),
                source_uri=f"dailymed://{label.setid}",
                title=label.title,
                embedder=embedder,
                max_age_days=max_age_days,
            )
        except Exception:
            log.warning(
                "dailymed_grounding_cache_failed",
                rxcui=rxcui,
                medication_id=str(grounding.medication_id),
                exc_info=True,
            )
            continue

        cached_count += 1

    log.info(
        "dailymed_grounding_cache_prepared",
        requested_count=requested_count,
        cached_count=cached_count,
    )
    return cached_count


async def _refresh_cached_document(
    session: AsyncSession,
    *,
    document: KnowledgeDocument,
    source: KnowledgeSource,
    source_uri: str,
    embedder: Embedder,
) -> KnowledgeDocument:
    """Refresh stale DailyMed chunks without discarding the old cache on failure."""
    try:
        source_chunks = [chunk async for chunk in source.list_chunks(document.id)]
        embeddings = await embedder([chunk.content for chunk in source_chunks])
        _validate_embedding_count(source_chunks, embeddings)
    except Exception:
        log.warning(
            "dailymed_cache_refresh_failed",
            document_id=str(document.id),
            source_uri=source_uri,
            exc_info=True,
        )
        return document

    await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
    _persist_chunks(
        session,
        document=document,
        source_chunks=source_chunks,
        embeddings=embeddings,
    )
    document.status = "ready"
    document.error_text = None
    document.updated_at = func.clock_timestamp()
    tokens_total = sum(chunk.tokens for chunk in source_chunks)
    session.add(
        AuditLogEntry(
            event_type="kb_doc_refreshed",
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
        "dailymed_cache_refreshed",
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
    source_uri: str,
) -> KnowledgeDocument | None:
    global_result = await session.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.source_type == "dailymed",
            KnowledgeDocument.source_uri == source_uri,
            KnowledgeDocument.uploaded_by == GLOBAL_DAILYMED_SCOPE_ID,
            KnowledgeDocument.status == "ready",
        )
    )
    global_document = global_result.scalar_one_or_none()
    if global_document is not None:
        return global_document

    legacy_result = await session.execute(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.source_type == "dailymed",
            KnowledgeDocument.source_uri == source_uri,
            KnowledgeDocument.status == "ready",
        )
        .limit(1)
    )
    legacy_document = legacy_result.scalar_one_or_none()
    if legacy_document is None:
        return None

    # Previous development builds cached DailyMed per workspace. Promote a
    # matching public label instead of creating another copy immediately.
    legacy_document.uploaded_by = GLOBAL_DAILYMED_SCOPE_ID
    await session.flush()
    log.info("dailymed_cache_promoted_to_global", document_id=str(legacy_document.id))
    return legacy_document


def _cache_is_stale(updated_at: datetime, *, max_age_days: int) -> bool:
    if max_age_days <= 0:
        return True
    return updated_at <= datetime.now(UTC) - timedelta(days=max_age_days)


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
