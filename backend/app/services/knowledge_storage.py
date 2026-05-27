"""Storage adapter for user-uploaded knowledge source files.

Routes should not know how a source file is stored. Today the adapter writes to
local disk for development; the same call sites can later use object storage
without changing upload, delete, or ingestion worker behavior.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

import structlog

from app.agents.knowledge_sources.user_upload import UserUploadSource
from app.config import Settings
from app.db.models import KnowledgeDocument

log = structlog.get_logger(__name__)


class KnowledgeStorage(Protocol):
    """Storage contract used by upload, delete, and ingestion worker routes."""

    def save(self, document_id: UUID, data: bytes) -> Path:
        """Persist an uploaded source file and return its ingestion path."""
        ...

    def remove(self, document: KnowledgeDocument) -> bool:
        """Delete a stored upload file if the backend still has it."""
        ...

    def source_for(self, document: KnowledgeDocument) -> UserUploadSource:
        """Build the ingestion source for a persisted user-upload document."""
        ...

    def source_from_metadata(
        self,
        *,
        document_id: UUID,
        mime: str,
        title: str,
        source_uri: str,
    ) -> UserUploadSource:
        """Build an ingestion source from committed document metadata."""
        ...

    def source_uri(self, document_id: UUID, title: str) -> str:
        """Build the source URI stored in the knowledge document row."""
        ...


@dataclass(frozen=True)
class LocalKnowledgeStorage:
    upload_dir: Path

    def save(self, document_id: UUID, data: bytes) -> Path:
        """Persist an uploaded source file and return its local ingestion path."""
        path = self.path_for(document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def remove(self, document: KnowledgeDocument) -> bool:
        """Delete a stored upload file if it still exists."""
        if document.source_type != "user_upload":
            return False

        path = self.path_for(document.id)
        if not path.exists():
            log.info("kb_doc_upload_file_missing", document_id=str(document.id))
            return False

        path.unlink()
        return True

    def source_for(self, document: KnowledgeDocument) -> UserUploadSource:
        """Build the ingestion source for a persisted user-upload document."""
        return self.source_from_metadata(
            document_id=document.id,
            mime=document.mime,
            title=document.title,
            source_uri=document.source_uri,
        )

    def source_from_metadata(
        self,
        *,
        document_id: UUID,
        mime: str,
        title: str,
        source_uri: str,
    ) -> UserUploadSource:
        """Build an ingestion source when only committed document metadata is available."""
        return UserUploadSource(
            path=self.path_for(document_id),
            mime=mime,
            title=title,
            source_uri=source_uri,
        )

    def path_for(self, document_id: UUID) -> Path:
        return self.upload_dir / f"{document_id}.bin"

    def source_uri(self, document_id: UUID, title: str) -> str:
        return f"local://kb/{document_id}/{title}"


def build_local_knowledge_storage(upload_dir: str) -> LocalKnowledgeStorage:
    return LocalKnowledgeStorage(upload_dir=Path(upload_dir))


def build_knowledge_storage(settings: Settings) -> KnowledgeStorage:
    if settings.knowledge_storage_backend == "local":
        return build_local_knowledge_storage(settings.knowledge_upload_dir)
    raise ValueError("unsupported knowledge storage backend")
