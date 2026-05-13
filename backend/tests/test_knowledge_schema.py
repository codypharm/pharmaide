"""Knowledge-base persistence smoke tests.

These tests stay at the schema boundary for the first 3.6a slice: they
prove migrations expose the document/chunk tables before ingestion or
retrieval code depends on them.
"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeDocument


async def test_kb_document_and_chunk_tables_are_migrated(
    db_session: AsyncSession,
) -> None:
    document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/example.pdf",
        title="Clinic protocol",
        mime="application/pdf",
        status="ingesting",
    )
    db_session.add(document)
    await db_session.flush()

    fetched = await db_session.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.id == document.id)
    )
    assert fetched is not None
    assert fetched.title == "Clinic protocol"

    chunks_column = await db_session.scalar(
        text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'kb_chunks'
              AND column_name = 'embedding'
            """
        )
    )
    assert chunks_column == "USER-DEFINED"
