"""Knowledge source storage adapter behavior."""

from uuid import uuid4

from app.config import Settings
from app.db.models import KnowledgeDocument
from app.services.knowledge_storage import LocalKnowledgeStorage, build_knowledge_storage


def test_local_knowledge_storage_saves_builds_source_and_removes_upload(tmp_path) -> None:
    storage = LocalKnowledgeStorage(tmp_path)
    document_id = uuid4()

    path = storage.save(document_id, b"Clinic protocol text")
    source_uri = storage.source_uri(document_id, "protocol.txt")
    document = KnowledgeDocument(
        id=document_id,
        source_type="user_upload",
        source_uri=source_uri,
        title="protocol.txt",
        mime="text/plain",
        status="ready",
    )

    source = storage.source_for(document)

    assert path == tmp_path / f"{document_id}.bin"
    assert path.read_bytes() == b"Clinic protocol text"
    assert source.path == path
    assert source.mime == "text/plain"
    assert source.title == "protocol.txt"
    assert source.source_uri == source_uri
    assert storage.remove(document) is True
    assert not path.exists()


def test_local_knowledge_storage_remove_is_idempotent_for_missing_file(tmp_path) -> None:
    storage = LocalKnowledgeStorage(tmp_path)
    document = KnowledgeDocument(
        id=uuid4(),
        source_type="user_upload",
        source_uri="local://kb/missing",
        title="missing.txt",
        mime="text/plain",
        status="ready",
    )

    assert storage.remove(document) is False


def test_build_knowledge_storage_selects_local_backend(tmp_path) -> None:
    storage = build_knowledge_storage(
        Settings(
            _env_file=None,
            knowledge_storage_backend="local",
            knowledge_upload_dir=str(tmp_path),
        )
    )

    assert isinstance(storage, LocalKnowledgeStorage)
    assert storage.upload_dir == tmp_path
