"""Internal worker seam for queued knowledge ingestion jobs."""

from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.knowledge_sources.user_upload import UserUploadSource
from app.config import Settings, get_settings
from app.db.models import KnowledgeDocument


@pytest.mark.usefixtures("postgres_container")
async def test_run_knowledge_ingestion_worker_executes_document_job(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    test_app: FastAPI,
    tmp_path: Path,
) -> None:
    document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/protocol.txt",
        title="protocol.txt",
        mime="text/plain",
        status="ingesting",
        uploaded_by=uuid4(),
    )
    db_session.add(document)
    await db_session.flush()
    (tmp_path / f"{document.id}.bin").write_bytes(b"Warfarin requires INR monitoring.")
    seen: dict[str, object] = {}

    async def fake_ingest_document(
        session_factory: async_sessionmaker[AsyncSession],
        document_id: UUID,
        *,
        source: UserUploadSource,
        embedder: object,
    ) -> None:
        seen["document_id"] = document_id
        seen["source"] = source
        seen["embedder"] = embedder
        async with session_factory() as session, session.begin():
            row = await session.get(KnowledgeDocument, document_id)
            assert row is not None
            row.status = "ready"

    monkeypatch.setattr("app.api.internal.ingest_document", fake_ingest_document)
    monkeypatch.setattr("app.api.internal._knowledge_embedder", lambda _api_key: _embed)
    test_app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        knowledge_upload_dir=str(tmp_path),
    )

    response = await app_client.post(f"/internal/knowledge/documents/{document.id}/ingest")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "document_id": str(document.id),
        "status": "ready",
    }
    assert seen["document_id"] == document.id
    source = seen["source"]
    assert isinstance(source, UserUploadSource)
    assert source.path == tmp_path / f"{document.id}.bin"
    assert source.mime == "text/plain"
    assert source.title == "protocol.txt"
    assert source.source_uri == "local://kb/protocol.txt"


@pytest.mark.usefixtures("postgres_container")
async def test_run_knowledge_ingestion_worker_returns_404_for_unknown_document(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post(f"/internal/knowledge/documents/{uuid4()}/ingest")

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "knowledge_document_not_found"}}


async def _embed(texts: Sequence[str]) -> list[list[float]]:
    return [[0.0] * 3072 for _text in texts]
