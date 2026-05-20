"""Deterministic retrieval-scope evaluation cases.

These cases protect the production invariant that pharmacist-uploaded knowledge
is scoped to the current clinic/workspace. Public DailyMed chunks may be shared,
but another pharmacist's uploaded protocol must never be returned.
"""

from collections.abc import Sequence
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EMBEDDING_DIMENSIONS, KnowledgeChunk, KnowledgeDocument
from app.services.kb_retrieval import retrieve
from app.services.kb_scope import GLOBAL_DAILYMED_SCOPE_ID

pytestmark = pytest.mark.clinical_eval


async def test_retrieval_eval_excludes_other_workspace_uploaded_documents(
    db_session: AsyncSession,
) -> None:
    current_scope_id = UUID("11111111-1111-4111-8111-111111111111")
    other_scope_id = UUID("22222222-2222-4222-8222-222222222222")
    current_document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://clinic-a/protocol.pdf",
        title="Clinic A Protocol",
        mime="application/pdf",
        status="ready",
        uploaded_by=current_scope_id,
    )
    other_document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://clinic-b/private-protocol.pdf",
        title="Clinic B Private Protocol",
        mime="application/pdf",
        status="ready",
        uploaded_by=other_scope_id,
    )
    dailymed_document = KnowledgeDocument(
        source_type="dailymed",
        source_uri="dailymed://public-label",
        title="Public DailyMed Label",
        mime="application/spl+xml",
        status="ready",
        uploaded_by=GLOBAL_DAILYMED_SCOPE_ID,
    )
    db_session.add_all([current_document, other_document, dailymed_document])
    await db_session.flush()
    db_session.add_all(
        [
            _chunk(current_document.id, "Clinic A dosing protocol may be cited."),
            _chunk(other_document.id, "Clinic B private protocol must not leak."),
            _chunk(dailymed_document.id, "Public DailyMed label may be cited."),
        ]
    )
    await db_session.flush()

    citations = await retrieve(
        db_session,
        "dosing protocol",
        embedder=_embed_query,
        uploaded_by=current_scope_id,
    )

    assert {citation.text for citation in citations} == {
        "Clinic A dosing protocol may be cited.",
        "Public DailyMed label may be cited.",
    }
    assert "Clinic B private protocol must not leak." not in {
        citation.text for citation in citations
    }


def _chunk(document_id: UUID, content: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        document_id=document_id,
        ordinal=0,
        content=content,
        embedding=_vector_literal(_embedding()),
        tokens=8,
    )


async def _embed_query(_texts: Sequence[str]) -> list[list[float]]:
    return [_embedding()]


def _embedding() -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[0] = 1.0
    return vector


def _vector_literal(embedding: Sequence[float]) -> str:
    return f"[{','.join(str(value) for value in embedding)}]"
