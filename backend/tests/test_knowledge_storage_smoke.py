"""Knowledge storage smoke command behavior."""

from uuid import UUID

from app.config import Settings
from app.services.knowledge_storage import GCSKnowledgeStorage, LocalKnowledgeStorage
from app.services.knowledge_storage_smoke import run_knowledge_storage_smoke
from tests.test_knowledge_storage import FakeGCSClient


async def test_knowledge_storage_smoke_roundtrips_local_storage(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        knowledge_storage_backend="local",
        knowledge_upload_dir=str(tmp_path),
    )

    report = await run_knowledge_storage_smoke(
        settings,
        document_id=UUID("00000000-0000-4000-8000-000000000001"),
    )

    assert report.ok is True
    assert report.backend == "local"
    assert report.read_chunk_count == 1
    assert report.removed is True
    assert report.errors == ()
    assert not list(tmp_path.iterdir())


async def test_knowledge_storage_smoke_roundtrips_gcs_storage() -> None:
    settings = Settings(
        _env_file=None,
        knowledge_storage_backend="gcs",
        knowledge_gcs_bucket="pharmaide-kb",
        knowledge_gcs_prefix="clinic-assets",
    )
    client = FakeGCSClient()
    storage = GCSKnowledgeStorage(
        bucket_name="pharmaide-kb",
        prefix="clinic-assets",
        client=client,
    )

    report = await run_knowledge_storage_smoke(
        settings,
        storage=storage,
        document_id=UUID("00000000-0000-4000-8000-000000000002"),
    )

    assert report.ok is True
    assert report.backend == "gcs"
    assert report.source_uri == (
        "gcs://pharmaide-kb/clinic-assets/00000000-0000-4000-8000-000000000002.bin"
    )
    assert report.removed is True
    assert client.buckets["pharmaide-kb"].objects == {}


async def test_knowledge_storage_smoke_reports_cleanup_failure(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        knowledge_storage_backend="local",
        knowledge_upload_dir=str(tmp_path),
    )
    storage = RemoveFailsStorage(tmp_path)

    report = await run_knowledge_storage_smoke(settings, storage=storage)

    assert report.ok is False
    assert "probe_object_not_removed" in report.errors


class RemoveFailsStorage(LocalKnowledgeStorage):
    def remove(self, document) -> bool:  # type: ignore[no-untyped-def]
        return False
