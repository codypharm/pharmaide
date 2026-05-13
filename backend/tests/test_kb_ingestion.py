"""Knowledge-base ingestion service tests."""

from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.knowledge_sources import KnowledgeSourceChunk
from app.db.models import EMBEDDING_DIMENSIONS, AuditLogEntry, KnowledgeChunk, KnowledgeDocument
from app.services.kb_ingestion import ingest_document


class _MemorySource:
    async def list_chunks(self, document_id: UUID) -> AsyncIterator[KnowledgeSourceChunk]:
        yield KnowledgeSourceChunk(
            content="Warfarin requires INR monitoring.",
            tokens=5,
            source_uri=f"memory://{document_id}/1",
            document_title="Anticoagulation Protocol",
        )
        yield KnowledgeSourceChunk(
            content="Avoid NSAIDs while on warfarin.",
            tokens=5,
            source_uri=f"memory://{document_id}/2",
            document_title="Anticoagulation Protocol",
        )


class _FailingSource:
    async def list_chunks(self, document_id: UUID) -> AsyncIterator[KnowledgeSourceChunk]:
        raise RuntimeError(f"parser failed for {document_id}")
        yield


async def _embed(texts: Sequence[str]) -> list[list[float]]:
    return [[float(index)] * EMBEDDING_DIMENSIONS for index, _text in enumerate(texts, start=1)]


async def test_ingest_document_persists_chunks_and_non_phi_audit(
    db_session: AsyncSession,
) -> None:
    document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/warfarin.pdf",
        title="Anticoagulation Protocol",
        mime="application/pdf",
        status="ingesting",
    )
    db_session.add(document)
    await db_session.flush()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    await ingest_document(session_factory, document.id, source=_MemorySource(), embedder=_embed)

    await db_session.refresh(document)
    chunks = list(
        (
            await db_session.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == document.id)
                .order_by(KnowledgeChunk.ordinal)
            )
        ).scalars()
    )
    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == document.id,
            AuditLogEntry.event_type == "kb_doc_ingested",
        )
    )

    assert document.status == "ready"
    assert document.error_text is None
    assert [chunk.ordinal for chunk in chunks] == [0, 1]
    assert [chunk.content for chunk in chunks] == [
        "Warfarin requires INR monitoring.",
        "Avoid NSAIDs while on warfarin.",
    ]
    assert [chunk.tokens for chunk in chunks] == [5, 5]
    assert audit is not None
    assert audit.resource_type == "kb_document"
    assert audit.payload == {
        "document_id": str(document.id),
        "chunk_count": 2,
        "tokens_total": 10,
    }


async def test_ingest_document_marks_failed_and_audits_without_source_text(
    db_session: AsyncSession,
) -> None:
    document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/broken.pdf",
        title="Broken Protocol",
        mime="application/pdf",
        status="ingesting",
    )
    db_session.add(document)
    await db_session.flush()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    await ingest_document(session_factory, document.id, source=_FailingSource(), embedder=_embed)

    await db_session.refresh(document)
    chunk_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document.id)
    )
    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == document.id,
            AuditLogEntry.event_type == "kb_doc_ingestion_failed",
        )
    )

    assert document.status == "failed"
    assert document.error_text == "ingestion_failed"
    assert chunk_count == 0
    assert audit is not None
    assert audit.payload == {
        "document_id": str(document.id),
        "error": "ingestion_failed",
    }
