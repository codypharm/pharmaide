"""Knowledge document API route behavior."""

import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import EMBEDDING_DIMENSIONS, AuditLogEntry, KnowledgeChunk, KnowledgeDocument
from app.services import task_runner


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
    db_session.add_all([document, other_document])
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

    assert list_response.status_code == 200
    assert list_response.json()["items"] == [
        {
            "id": str(document.id),
            "title": "Anticoagulation Protocol",
            "mime": "application/pdf",
            "status": "ready",
            "chunk_count": 2,
            "created_at": document.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": document.updated_at.isoformat().replace("+00:00", "Z"),
        }
    ]
    assert get_response.status_code == 200
    assert get_response.json()["chunk_count"] == 2
    assert cross_scope_response.status_code == 404


@pytest.mark.usefixtures("postgres_container")
async def test_delete_knowledge_document_soft_removes_it_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
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

    assert response.status_code == 204
    assert document.status == "removed"
    assert audit is not None
    assert audit.payload == {"document_id": str(document.id)}


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
