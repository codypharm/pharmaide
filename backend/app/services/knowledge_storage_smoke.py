"""Smoke check for configured knowledge source storage.

This verifies the operational storage path without using patient data: write a
small synthetic probe, read it through the ingestion source, then delete it.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.config import Settings
from app.db.models import KnowledgeDocument
from app.services.knowledge_storage import KnowledgeStorage, build_knowledge_storage

SMOKE_TITLE = "pharmaide-storage-smoke.txt"
SMOKE_MIME = "text/plain"
SMOKE_BYTES = b"PharmaAide knowledge storage smoke probe."


@dataclass(frozen=True)
class KnowledgeStorageSmokeReport:
    backend: str
    ok: bool
    source_uri: str | None
    read_chunk_count: int
    removed: bool
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "backend": self.backend,
            "source_uri": self.source_uri,
            "read_chunk_count": self.read_chunk_count,
            "removed": self.removed,
            "errors": list(self.errors),
        }


async def run_knowledge_storage_smoke(
    settings: Settings,
    *,
    storage: KnowledgeStorage | None = None,
    document_id: UUID | None = None,
) -> KnowledgeStorageSmokeReport:
    """Write, read, and remove a synthetic upload through the configured adapter."""
    document_id = document_id or uuid4()
    selected_storage = storage or build_knowledge_storage(settings)
    source_uri: str | None = None
    read_chunk_count = 0
    removed = False
    errors: list[str] = []
    document = _smoke_document(document_id, source_uri="")

    try:
        selected_storage.save(document_id, SMOKE_BYTES)
        source_uri = selected_storage.source_uri(document_id, SMOKE_TITLE)
        document = _smoke_document(document_id, source_uri=source_uri)
        chunks = [
            chunk
            async for chunk in selected_storage.source_from_metadata(
                document_id=document_id,
                mime=SMOKE_MIME,
                title=SMOKE_TITLE,
                source_uri=source_uri,
            ).list_chunks(document_id)
        ]
        read_chunk_count = len(chunks)
        if not any("knowledge storage smoke probe" in chunk.content for chunk in chunks):
            errors.append("probe_content_not_read_back")
    except Exception as exc:
        errors.append(f"{exc.__class__.__name__}: {exc}")
    finally:
        try:
            removed = selected_storage.remove(document)
            if not removed:
                errors.append("probe_object_not_removed")
        except Exception as exc:
            errors.append(f"remove_failed:{exc.__class__.__name__}: {exc}")

    return KnowledgeStorageSmokeReport(
        backend=settings.knowledge_storage_backend,
        ok=not errors,
        source_uri=source_uri,
        read_chunk_count=read_chunk_count,
        removed=removed,
        errors=tuple(errors),
    )


def _smoke_document(document_id: UUID, *, source_uri: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=document_id,
        source_type="user_upload",
        source_uri=source_uri,
        title=SMOKE_TITLE,
        mime=SMOKE_MIME,
        status="ready",
    )
