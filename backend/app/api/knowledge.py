"""Knowledge-base document route handlers."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.knowledge_sources.user_upload import UserUploadSource
from app.config import Settings, get_settings
from app.db.engine import get_session, get_session_factory
from app.db.models import AuditLogEntry, KnowledgeChunk, KnowledgeDocument
from app.services import task_runner
from app.services.embeddings import build_embedding_client, embed_texts
from app.services.kb_ingestion import ingest_document

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ActorDep = Annotated[UUID, Header(alias="X-Pharmaide-User-Id")]

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
}

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/knowledge")


class KnowledgeDocumentCreated(BaseModel):
    document_id: UUID
    status: str


class KnowledgeDocumentView(BaseModel):
    id: UUID
    title: str
    mime: str
    status: str
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentList(BaseModel):
    items: list[KnowledgeDocumentView] = Field(default_factory=list)


@router.post(
    "/documents",
    status_code=202,
    response_model=KnowledgeDocumentCreated,
)
async def upload_document(
    session_factory: SessionFactoryDep,
    settings: SettingsDep,
    actor_id: ActorDep,
    file: Annotated[UploadFile, File()],
) -> KnowledgeDocumentCreated:
    mime = _supported_mime(file.content_type)
    data = await file.read()
    _validate_size(data, settings.knowledge_max_upload_bytes)

    title = _safe_title(file.filename)
    async with session_factory() as session, session.begin():
        document = KnowledgeDocument(
            source_type="user_upload",
            source_uri="pending://kb-upload",
            title=title,
            mime=mime,
            status="ingesting",
            uploaded_by=actor_id,
        )
        session.add(document)
        await session.flush()

        storage_path = _storage_path(settings.knowledge_upload_dir, document.id)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(data)
        document.source_uri = _source_uri(document.id, title)
        _audit_uploaded(session, document_id=document.id, size_bytes=len(data), mime=mime)
        document_id = document.id
        source_uri = document.source_uri
        status = document.status

    task_runner.schedule(
        ingest_document,
        session_factory,
        document_id,
        source=UserUploadSource(
            path=storage_path,
            mime=mime,
            title=title,
            source_uri=source_uri,
        ),
        embedder=_embedder(settings.openai_api_key),
    )
    log.info(
        "kb_doc_upload_scheduled",
        document_id=str(document_id),
        mime=mime,
        size_bytes=len(data),
        actor_id=str(actor_id),
    )
    return KnowledgeDocumentCreated(document_id=document_id, status=status)


@router.get("/documents", response_model=KnowledgeDocumentList)
async def list_documents(
    session: SessionDep,
    actor_id: ActorDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KnowledgeDocumentList:
    rows = await _document_rows(session, actor_id=actor_id, limit=limit, offset=offset)
    return KnowledgeDocumentList(items=[_document_view(row) for row in rows])


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentView)
async def get_document(
    document_id: UUID,
    session: SessionDep,
    actor_id: ActorDep,
) -> KnowledgeDocumentView:
    row = await _document_row(session, document_id=document_id, actor_id=actor_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "knowledge_document_not_found"})
    return _document_view(row)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    session: SessionDep,
    settings: SettingsDep,
    actor_id: ActorDep,
) -> Response:
    row = await session.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.uploaded_by == actor_id,
            KnowledgeDocument.status != "removed",
        )
    )
    document = row.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail={"error": "knowledge_document_not_found"})

    stored_file_removed = _remove_stored_upload(settings.knowledge_upload_dir, document)
    chunk_count_removed = await _remove_document_chunks(session, document_id)
    document.status = "removed"
    document.updated_at = func.clock_timestamp()
    session.add(
        AuditLogEntry(
            event_type="kb_doc_removed",
            resource_type="kb_document",
            resource_id=document_id,
            payload={
                "document_id": str(document_id),
                "stored_file_removed": stored_file_removed,
                "chunk_count_removed": chunk_count_removed,
            },
        )
    )
    log.info(
        "kb_doc_removed",
        document_id=str(document_id),
        actor_id=str(actor_id),
        stored_file_removed=stored_file_removed,
        chunk_count_removed=chunk_count_removed,
    )
    return Response(status_code=204)


async def _document_rows(
    session: AsyncSession,
    *,
    actor_id: UUID,
    limit: int,
    offset: int,
) -> list[tuple[KnowledgeDocument, int]]:
    result = await session.execute(
        select(KnowledgeDocument, func.count(KnowledgeChunk.id))
        .outerjoin(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeDocument.uploaded_by == actor_id,
            KnowledgeDocument.status != "removed",
        )
        .group_by(KnowledgeDocument.id)
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.all())


async def _document_row(
    session: AsyncSession,
    *,
    document_id: UUID,
    actor_id: UUID,
) -> tuple[KnowledgeDocument, int] | None:
    result = await session.execute(
        select(KnowledgeDocument, func.count(KnowledgeChunk.id))
        .outerjoin(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.uploaded_by == actor_id,
            KnowledgeDocument.status != "removed",
        )
        .group_by(KnowledgeDocument.id)
    )
    return result.one_or_none()


def _document_view(row: tuple[KnowledgeDocument, int]) -> KnowledgeDocumentView:
    document, chunk_count = row
    return KnowledgeDocumentView(
        id=document.id,
        title=document.title,
        mime=document.mime,
        status=document.status,
        chunk_count=chunk_count,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _supported_mime(mime: str | None) -> str:
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=422, detail={"error": "unsupported_knowledge_file_type"})
    return mime


def _validate_size(data: bytes, max_upload_bytes: int) -> None:
    if len(data) > max_upload_bytes:
        raise HTTPException(status_code=422, detail={"error": "knowledge_file_too_large"})
    if not data:
        raise HTTPException(status_code=422, detail={"error": "empty_knowledge_file"})


def _safe_title(filename: str | None) -> str:
    title = Path(filename or "knowledge-upload").name.strip()
    return title or "knowledge-upload"


def _storage_path(upload_dir: str, document_id: UUID) -> Path:
    return Path(upload_dir) / f"{document_id}.bin"


async def _remove_document_chunks(session: AsyncSession, document_id: UUID) -> int:
    result = await session.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
    )
    return int(result.rowcount or 0)


def _remove_stored_upload(upload_dir: str, document: KnowledgeDocument) -> bool:
    if document.source_type != "user_upload":
        return False

    path = _storage_path(upload_dir, document.id)
    if not path.exists():
        log.info("kb_doc_upload_file_missing", document_id=str(document.id))
        return False

    path.unlink()
    return True


def _source_uri(document_id: UUID, title: str) -> str:
    return f"local://kb/{document_id}/{title}"


def _audit_uploaded(
    session: AsyncSession,
    *,
    document_id: UUID,
    size_bytes: int,
    mime: str,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="kb_doc_uploaded",
            resource_type="kb_document",
            resource_id=document_id,
            payload={
                "document_id": str(document_id),
                "size_bytes": size_bytes,
                "mime": mime,
            },
        )
    )


def _embedder(openai_api_key: SecretStr | None):
    async def embed(texts: Sequence[str]) -> list[list[float]]:
        client = build_embedding_client(openai_api_key)
        try:
            return await embed_texts(texts, client=client)
        finally:
            await client.close()

    return embed
