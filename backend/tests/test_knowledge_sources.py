"""Knowledge-source contract tests."""

from collections.abc import AsyncIterator
from uuid import UUID

from app.agents.knowledge_sources import KnowledgeSource, KnowledgeSourceChunk
from app.agents.knowledge_sources.user_upload import UserUploadSource


class _MemorySource:
    async def list_chunks(self, document_id: UUID) -> AsyncIterator[KnowledgeSourceChunk]:
        yield KnowledgeSourceChunk(
            content="Warfarin requires INR monitoring.",
            tokens=5,
            source_uri=f"memory://{document_id}",
            document_title="Anticoagulation Protocol",
            page_number=2,
        )


async def test_knowledge_source_protocol_yields_retrievable_chunks() -> None:
    document_id = UUID("00000000-0000-0000-0000-000000000123")
    source: KnowledgeSource = _MemorySource()

    chunks = [chunk async for chunk in source.list_chunks(document_id)]

    assert chunks == [
        KnowledgeSourceChunk(
            content="Warfarin requires INR monitoring.",
            tokens=5,
            source_uri="memory://00000000-0000-0000-0000-000000000123",
            document_title="Anticoagulation Protocol",
            page_number=2,
        )
    ]


async def test_user_upload_source_reads_stored_text_upload(tmp_path) -> None:
    path = tmp_path / "upload.txt"
    path.write_text("Warfarin requires INR monitoring.", encoding="utf-8")
    source = UserUploadSource(
        path=path,
        mime="text/plain",
        title="Anticoagulation Protocol",
        source_uri="local://kb/protocol.txt",
    )

    chunks = [chunk async for chunk in source.list_chunks(UUID(int=1))]

    assert len(chunks) == 1
    assert chunks[0].content.startswith("Document: Anticoagulation Protocol")
    assert "Warfarin requires INR monitoring." in chunks[0].content
    assert chunks[0].source_uri == "local://kb/protocol.txt"
    assert chunks[0].document_title == "Anticoagulation Protocol"
