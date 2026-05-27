"""Knowledge source storage adapter behavior."""

from uuid import uuid4

from app.config import Settings
from app.db.models import KnowledgeDocument
from app.services.knowledge_storage import (
    GCSKnowledgeStorage,
    LocalKnowledgeStorage,
    build_knowledge_storage,
)


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


async def test_gcs_knowledge_storage_saves_sources_and_removes_upload() -> None:
    client = FakeGCSClient()
    storage = GCSKnowledgeStorage(
        bucket_name="pharmaide-kb",
        prefix="clinic-assets",
        client=client,
    )
    document_id = uuid4()

    location = storage.save(document_id, b"Clinic CSV")
    source_uri = storage.source_uri(document_id, "products.csv")
    document = KnowledgeDocument(
        id=document_id,
        source_type="user_upload",
        source_uri=source_uri,
        title="products.csv",
        mime="text/plain",
        status="ready",
    )
    source = storage.source_for(document)
    chunks = [chunk async for chunk in source.list_chunks(document_id)]

    assert location == f"clinic-assets/{document_id}.bin"
    assert source_uri == f"gcs://pharmaide-kb/clinic-assets/{document_id}.bin"
    assert chunks[0].content.startswith("Document: products.csv")
    assert "Clinic CSV" in chunks[0].content
    assert storage.remove(document) is True
    assert storage.remove(document) is False


def test_build_knowledge_storage_selects_gcs_backend() -> None:
    storage = build_knowledge_storage(
        Settings(
            _env_file=None,
            knowledge_storage_backend="gcs",
            knowledge_gcs_bucket="pharmaide-kb",
            knowledge_gcs_prefix="clinic-assets",
        )
    )

    assert isinstance(storage, GCSKnowledgeStorage)
    assert storage.bucket_name == "pharmaide-kb"
    assert storage.prefix == "clinic-assets"


class FakeGCSClient:
    def __init__(self) -> None:
        self.buckets: dict[str, FakeGCSBucket] = {}

    def bucket(self, name: str) -> "FakeGCSBucket":
        if name not in self.buckets:
            self.buckets[name] = FakeGCSBucket()
        return self.buckets[name]


class FakeGCSBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def blob(self, name: str) -> "FakeGCSBlob":
        return FakeGCSBlob(name=name, bucket=self)


class FakeGCSBlob:
    def __init__(self, *, name: str, bucket: FakeGCSBucket) -> None:
        self.name = name
        self.bucket = bucket

    def upload_from_string(self, data: bytes, *, content_type: str) -> None:
        assert content_type == "application/octet-stream"
        self.bucket.objects[self.name] = data

    def download_as_bytes(self) -> bytes:
        return self.bucket.objects[self.name]

    def exists(self) -> bool:
        return self.name in self.bucket.objects

    def delete(self) -> None:
        del self.bucket.objects[self.name]
