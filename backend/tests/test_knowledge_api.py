"""Knowledge document API route behavior."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import EMBEDDING_DIMENSIONS, AuditLogEntry, KnowledgeChunk, KnowledgeDocument
from app.services import task_runner
from app.services.kb_scope import GLOBAL_DAILYMED_SCOPE_ID


@pytest.mark.usefixtures("postgres_container")
async def test_upload_knowledge_document_stores_file_schedules_ingestion_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_app: FastAPI,
) -> None:
    scheduled: dict[str, object] = {}

    def capture_schedule(
        coro_fn: Callable[..., object],
        *args: object,
        **kwargs: object,
    ) -> None:
        scheduled["coro_fn"] = coro_fn
        scheduled["args"] = args
        scheduled["kwargs"] = kwargs

    monkeypatch.setattr(task_runner, "schedule", capture_schedule)
    test_app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        knowledge_upload_dir=str(tmp_path),
    )

    actor_id = uuid4()
    response = await app_client.post(
        "/knowledge/documents",
        headers={"X-Pharmaide-User-Id": str(actor_id)},
        files={"file": ("warfarin.txt", b"Warfarin requires INR monitoring.", "text/plain")},
    )

    assert response.status_code == 202
    body = response.json()
    document_id = UUID(body["document_id"])
    assert body["status"] == "ingesting"

    document = await db_session.get(KnowledgeDocument, document_id)
    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == document_id,
            AuditLogEntry.event_type == "kb_doc_uploaded",
        )
    )

    assert document is not None
    assert document.title == "warfarin.txt"
    assert document.mime == "text/plain"
    assert document.status == "ingesting"
    assert document.uploaded_by == actor_id
    assert document.source_uri == f"local://kb/{document_id}/warfarin.txt"
    assert (tmp_path / f"{document_id}.bin").read_bytes() == b"Warfarin requires INR monitoring."
    assert scheduled["coro_fn"].__name__ == "ingest_document"
    assert scheduled["args"][1] == document_id
    assert "source" in scheduled["kwargs"]
    assert "embedder" in scheduled["kwargs"]
    assert audit is not None
    assert audit.payload == {
        "document_id": str(document_id),
        "size_bytes": len(b"Warfarin requires INR monitoring."),
        "mime": "text/plain",
    }
    assert "Warfarin" not in json.dumps(audit.payload)


@pytest.mark.usefixtures("postgres_container")
async def test_list_and_get_knowledge_documents_return_metadata_with_chunk_count(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner_id = uuid4()
    other_owner_id = uuid4()
    document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/anticoagulation.pdf",
        title="Anticoagulation Protocol",
        mime="application/pdf",
        status="ready",
        uploaded_by=owner_id,
    )
    other_document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/other.pdf",
        title="Other Clinic Protocol",
        mime="application/pdf",
        status="ready",
        uploaded_by=other_owner_id,
    )
    dailymed_document = KnowledgeDocument(
        source_type="dailymed",
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        mime="application/spl+xml",
        status="ready",
        uploaded_by=GLOBAL_DAILYMED_SCOPE_ID,
    )
    db_session.add_all([document, other_document, dailymed_document])
    await db_session.flush()
    db_session.add_all(
        [
            KnowledgeChunk(
                document_id=document.id,
                ordinal=0,
                content="INR monitoring guidance.",
                embedding=_vector_literal(0.0),
                tokens=3,
            ),
            KnowledgeChunk(
                document_id=document.id,
                ordinal=1,
                content="Bleeding risk guidance.",
                embedding=_vector_literal(1.0),
                tokens=3,
            ),
            KnowledgeChunk(
                document_id=dailymed_document.id,
                ordinal=0,
                content="DailyMed label warning.",
                embedding=_vector_literal(0.0),
                tokens=3,
            ),
        ]
    )
    await db_session.flush()

    list_response = await app_client.get(
        "/knowledge/documents",
        headers={"X-Pharmaide-User-Id": str(owner_id)},
    )
    get_response = await app_client.get(
        f"/knowledge/documents/{document.id}",
        headers={"X-Pharmaide-User-Id": str(owner_id)},
    )
    cross_scope_response = await app_client.get(
        f"/knowledge/documents/{other_document.id}",
        headers={"X-Pharmaide-User-Id": str(owner_id)},
    )
    dailymed_response = await app_client.get(
        f"/knowledge/documents/{dailymed_document.id}",
        headers={"X-Pharmaide-User-Id": str(owner_id)},
    )

    assert list_response.status_code == 200
    items_by_title = {item["title"]: item for item in list_response.json()["items"]}
    assert set(items_by_title) == {"Anticoagulation Protocol"}
    assert items_by_title["Anticoagulation Protocol"]["source_type"] == "user_upload"
    assert items_by_title["Anticoagulation Protocol"]["chunk_count"] == 2
    assert get_response.status_code == 200
    assert get_response.json()["chunk_count"] == 2
    assert dailymed_response.status_code == 200
    assert dailymed_response.json()["source_type"] == "dailymed"
    assert cross_scope_response.status_code == 404


@pytest.mark.usefixtures("postgres_container")
async def test_delete_knowledge_document_rejects_read_only_dailymed_reference(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    owner_id = uuid4()
    document = KnowledgeDocument(
        source_type="dailymed",
        source_uri="dailymed://setid-1",
        title="Lisinopril Tablet",
        mime="application/spl+xml",
        status="ready",
        uploaded_by=GLOBAL_DAILYMED_SCOPE_ID,
    )
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        KnowledgeChunk(
            document_id=document.id,
            ordinal=0,
            content="DailyMed warning.",
            embedding=_vector_literal(0.0),
            tokens=2,
        )
    )
    await db_session.flush()

    response = await app_client.delete(
        f"/knowledge/documents/{document.id}",
        headers={"X-Pharmaide-User-Id": str(owner_id)},
    )
    chunk_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document.id)
    )

    await db_session.refresh(document)
    assert response.status_code == 409
    assert response.json()["detail"] == {"error": "knowledge_document_read_only"}
    assert document.status == "ready"
    assert chunk_count == 1


@pytest.mark.usefixtures("postgres_container")
async def test_list_knowledge_documents_marks_stale_processing_assets_failed(
    app_client: AsyncClient,
    db_session: AsyncSession,
    test_app: FastAPI,
) -> None:
    test_app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        knowledge_ingestion_stale_minutes=5,
    )
    owner_id = uuid4()
    stale_document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/stale.csv",
        title="Stale Upload",
        mime="text/csv",
        status="ingesting",
        uploaded_by=owner_id,
        updated_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    fresh_document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/fresh.csv",
        title="Fresh Upload",
        mime="text/csv",
        status="ingesting",
        uploaded_by=owner_id,
        updated_at=datetime.now(UTC),
    )
    db_session.add_all([stale_document, fresh_document])
    await db_session.flush()

    response = await app_client.get(
        "/knowledge/documents",
        headers={"X-Pharmaide-User-Id": str(owner_id)},
    )

    await db_session.refresh(stale_document)
    await db_session.refresh(fresh_document)
    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == stale_document.id,
            AuditLogEntry.event_type == "kb_doc_ingestion_failed",
        )
    )
    statuses = {item["title"]: item["status"] for item in response.json()["items"]}

    assert response.status_code == 200
    assert statuses == {"Stale Upload": "failed", "Fresh Upload": "ingesting"}
    assert stale_document.status == "failed"
    assert stale_document.error_text == "ingestion_stale"
    assert fresh_document.status == "ingesting"
    assert audit is not None
    assert audit.payload == {
        "document_id": str(stale_document.id),
        "error": "ingestion_stale",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_delete_knowledge_document_soft_removes_it_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    test_app: FastAPI,
) -> None:
    test_app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        knowledge_upload_dir=str(tmp_path),
    )
    owner_id = uuid4()
    document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/anticoagulation.pdf",
        title="Anticoagulation Protocol",
        mime="application/pdf",
        status="ready",
        uploaded_by=owner_id,
    )
    db_session.add(document)
    await db_session.flush()
    stored_file = tmp_path / f"{document.id}.bin"
    stored_file.write_bytes(b"stored clinical asset")
    db_session.add(
        KnowledgeChunk(
            document_id=document.id,
            ordinal=0,
            content="Stored guidance.",
            embedding=_vector_literal(0.0),
            tokens=2,
        )
    )
    await db_session.flush()

    response = await app_client.delete(
        f"/knowledge/documents/{document.id}",
        headers={"X-Pharmaide-User-Id": str(owner_id)},
    )

    await db_session.refresh(document)
    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == document.id,
            AuditLogEntry.event_type == "kb_doc_removed",
        )
    )
    chunk_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document.id)
    )

    assert response.status_code == 204
    assert document.status == "removed"
    assert not stored_file.exists()
    assert chunk_count == 0
    assert audit is not None
    assert audit.payload == {
        "document_id": str(document.id),
        "stored_file_removed": True,
        "chunk_count_removed": 1,
    }


@pytest.mark.usefixtures("postgres_container")
async def test_upload_knowledge_document_rejects_unsupported_mime(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post(
        "/knowledge/documents",
        headers={"X-Pharmaide-User-Id": str(uuid4())},
        files={"file": ("notes.docx", b"opaque", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {"error": "unsupported_knowledge_file_type"}


def _vector_literal(value: float) -> str:
    return f"[{','.join(str(value) for _ in range(EMBEDDING_DIMENSIONS))}]"
