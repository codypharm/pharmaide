"""Knowledge-source contract tests."""

from collections.abc import AsyncIterator
from uuid import UUID

from app.agents.knowledge_sources import KnowledgeSource, KnowledgeSourceChunk


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
