"""DailyMed cache persistence tests."""

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analysis_schemas import MedicationGrounding
from app.agents.knowledge_sources import KnowledgeSourceChunk
from app.agents.knowledge_sources.dailymed import DailyMedClient
from app.db.models import EMBEDDING_DIMENSIONS, AuditLogEntry, KnowledgeChunk, KnowledgeDocument
from app.services.dailymed_cache import (
    ensure_dailymed_cached,
    ensure_dailymed_cached_for_groundings,
)
from app.services.kb_scope import GLOBAL_DAILYMED_SCOPE_ID


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
    source = _DailyMedMemorySource()

    document = await ensure_dailymed_cached(
        db_session,
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
    assert document.uploaded_by == GLOBAL_DAILYMED_SCOPE_ID
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
    existing = KnowledgeDocument(
        source_type="dailymed",
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        mime="application/spl+xml",
        status="ready",
        uploaded_by=GLOBAL_DAILYMED_SCOPE_ID,
    )
    db_session.add(existing)
    await db_session.flush()
    source = _DailyMedMemorySource()

    document = await ensure_dailymed_cached(
        db_session,
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


async def test_dailymed_cache_owner_uri_is_unique(
    db_session: AsyncSession,
) -> None:
    first = KnowledgeDocument(
        source_type="dailymed",
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        mime="application/spl+xml",
        status="ready",
        uploaded_by=GLOBAL_DAILYMED_SCOPE_ID,
    )
    db_session.add(first)
    await db_session.flush()

    duplicate = KnowledgeDocument(
        source_type="dailymed",
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet Duplicate",
        mime="application/spl+xml",
        status="ready",
        uploaded_by=GLOBAL_DAILYMED_SCOPE_ID,
    )

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(duplicate)
            await db_session.flush()

    document_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(
            KnowledgeDocument.source_type == "dailymed",
            KnowledgeDocument.source_uri == "dailymed://setid-1",
            KnowledgeDocument.uploaded_by == GLOBAL_DAILYMED_SCOPE_ID,
        )
    )
    assert document_count == 1


async def test_ensure_dailymed_cached_finishes_existing_in_progress_global_document(
    db_session: AsyncSession,
) -> None:
    existing = KnowledgeDocument(
        source_type="dailymed",
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        mime="application/spl+xml",
        status="ingesting",
        uploaded_by=GLOBAL_DAILYMED_SCOPE_ID,
    )
    db_session.add(existing)
    await db_session.flush()
    source = _DailyMedMemorySource()

    document = await ensure_dailymed_cached(
        db_session,
        source=source,
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        embedder=_embed,
    )
    chunk_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == existing.id)
    )
    document_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(KnowledgeDocument.source_uri == "dailymed://setid-1")
    )

    assert document.id == existing.id
    assert document.status == "ready"
    assert source.calls == 1
    assert chunk_count == 1
    assert document_count == 1


async def test_ensure_dailymed_cached_promotes_legacy_scoped_document_to_global(
    db_session: AsyncSession,
) -> None:
    legacy_scope_id = uuid4()
    legacy = KnowledgeDocument(
        source_type="dailymed",
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        mime="application/spl+xml",
        status="ready",
        uploaded_by=legacy_scope_id,
    )
    db_session.add(legacy)
    await db_session.flush()
    source = _DailyMedMemorySource()

    document = await ensure_dailymed_cached(
        db_session,
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
    assert document.id == legacy.id
    assert document.uploaded_by == GLOBAL_DAILYMED_SCOPE_ID
    assert source.calls == 0
    assert document_count == 1


async def test_ensure_dailymed_cached_refreshes_stale_global_document(
    db_session: AsyncSession,
) -> None:
    stale = KnowledgeDocument(
        source_type="dailymed",
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        mime="application/spl+xml",
        status="ready",
        uploaded_by=GLOBAL_DAILYMED_SCOPE_ID,
        updated_at=datetime.now(UTC) - timedelta(days=120),
    )
    db_session.add(stale)
    await db_session.flush()
    db_session.add(
        KnowledgeChunk(
            document_id=stale.id,
            ordinal=0,
            content="Old DailyMed label text.",
            embedding="[" + ",".join("0.0" for _ in range(EMBEDDING_DIMENSIONS)) + "]",
            tokens=4,
        )
    )
    await db_session.flush()
    source = _DailyMedMemorySource()

    document = await ensure_dailymed_cached(
        db_session,
        source=source,
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        embedder=_embed,
    )

    chunks = list(
        (
            await db_session.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == stale.id)
                .order_by(KnowledgeChunk.ordinal)
            )
        ).scalars()
    )
    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == stale.id,
            AuditLogEntry.event_type == "kb_doc_refreshed",
        )
    )

    assert document.id == stale.id
    assert source.calls == 1
    assert len(chunks) == 1
    assert chunks[0].content.endswith("Monitor dizziness.")
    assert audit is not None
    assert audit.payload["source_type"] == "dailymed"


async def test_ensure_dailymed_cached_for_groundings_fetches_one_label_per_rxcui(
    db_session: AsyncSession,
) -> None:
    medication_id = uuid4()
    search_calls = 0
    xml_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal search_calls, xml_calls
        if request.url.path == "/dailymed/services/v2/spls.json":
            search_calls += 1
            assert request.url.params["rxcui"] == "29046"
            return httpx.Response(
                200,
                json={"data": [{"setid": "setid-1", "title": "Lisinopril Tablet"}]},
            )
        if request.url.path == "/dailymed/services/v2/spls/setid-1.xml":
            xml_calls += 1
            return httpx.Response(200, text=_SPL_XML)
        return httpx.Response(404)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://dailymed.nlm.nih.gov",
    ) as http_client:
        cached_count = await ensure_dailymed_cached_for_groundings(
            db_session,
            groundings=[
                MedicationGrounding(
                    medication_id=medication_id,
                    medication_name="Lisinopril",
                    normalized_name="lisinopril",
                    rxcui="29046",
                    confidence=0.92,
                ),
                MedicationGrounding(
                    medication_id=uuid4(),
                    medication_name="Lisinopril Duplicate",
                    normalized_name="lisinopril",
                    rxcui="29046",
                    confidence=0.91,
                ),
            ],
            client=DailyMedClient(http_client=http_client),
            embedder=_embed,
        )

    document = await db_session.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.source_uri == "dailymed://setid-1")
    )
    assert document is not None
    chunk_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document.id)
    )

    assert cached_count == 1
    assert search_calls == 1
    assert xml_calls == 1
    assert document.status == "ready"
    assert document.uploaded_by == GLOBAL_DAILYMED_SCOPE_ID
    assert chunk_count == 1


_SPL_XML = """
<document xmlns="urn:hl7-org:v3">
  <component>
    <structuredBody>
      <component>
        <section>
          <title>Warnings and Precautions</title>
          <text><paragraph>Monitor for symptomatic hypotension.</paragraph></text>
        </section>
      </component>
    </structuredBody>
  </component>
</document>
"""
