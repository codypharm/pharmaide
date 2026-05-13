"""DailyMed cache persistence tests."""

from collections.abc import AsyncIterator, Sequence
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.knowledge_sources import KnowledgeSourceChunk
from app.db.models import EMBEDDING_DIMENSIONS, AuditLogEntry, KnowledgeChunk, KnowledgeDocument
from app.services.dailymed_cache import ensure_dailymed_cached


class _DailyMedMemorySource:
    def __init__(self) -> None:
        self.calls = 0

    async def list_chunks(self, _document_id: UUID) -> AsyncIterator[KnowledgeSourceChunk]:
        self.calls += 1
        yield KnowledgeSourceChunk(
            content="Document: Lisinopril Tablet\nSection: Warnings\n\nMonitor dizziness.",
            tokens=7,
            source_uri="dailymed://setid-1",
            document_title="Lisinopril Tablet",
            section_title="Warnings",
        )


async def _embed(texts: Sequence[str]) -> list[list[float]]:
    return [[float(index)] * EMBEDDING_DIMENSIONS for index, _text in enumerate(texts, start=1)]


async def test_ensure_dailymed_cached_persists_ready_document_chunks_and_audit(
    db_session: AsyncSession,
) -> None:
    scope_id = uuid4()
    source = _DailyMedMemorySource()

    document = await ensure_dailymed_cached(
        db_session,
        kb_scope_id=scope_id,
        source=source,
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        embedder=_embed,
    )

    chunks = list(
        (
            await db_session.execute(
                select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
            )
        ).scalars()
    )
    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == document.id,
            AuditLogEntry.event_type == "kb_doc_ingested",
        )
    )

    assert document.source_type == "dailymed"
    assert document.source_uri == "dailymed://setid-1"
    assert document.title == "Lisinopril Tablet"
    assert document.mime == "application/spl+xml"
    assert document.status == "ready"
    assert document.uploaded_by == scope_id
    assert source.calls == 1
    assert len(chunks) == 1
    assert chunks[0].content.endswith("Monitor dizziness.")
    assert chunks[0].tokens == 7
    assert audit is not None
    assert audit.payload == {
        "document_id": str(document.id),
        "source_type": "dailymed",
        "chunk_count": 1,
        "tokens_total": 7,
    }


async def test_ensure_dailymed_cached_returns_existing_ready_document_without_refetching(
    db_session: AsyncSession,
) -> None:
    scope_id = uuid4()
    existing = KnowledgeDocument(
        source_type="dailymed",
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        mime="application/spl+xml",
        status="ready",
        uploaded_by=scope_id,
    )
    db_session.add(existing)
    await db_session.flush()
    source = _DailyMedMemorySource()

    document = await ensure_dailymed_cached(
        db_session,
        kb_scope_id=scope_id,
        source=source,
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        embedder=_embed,
    )
    document_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(KnowledgeDocument.source_uri == "dailymed://setid-1")
    )

    assert document.id == existing.id
    assert source.calls == 0
    assert document_count == 1
