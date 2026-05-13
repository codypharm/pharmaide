"""Knowledge-base retrieval service tests."""

from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.kb_reranker import RerankedCitation, RerankResult
from app.db.models import EMBEDDING_DIMENSIONS, AuditLogEntry, KnowledgeChunk, KnowledgeDocument
from app.services.kb_retrieval import Citation, retrieve


def _embedding(axis: int) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[axis] = 1.0
    return vector


def _vector_literal(embedding: Sequence[float]) -> str:
    return f"[{','.join(str(value) for value in embedding)}]"


async def _embed_query(_texts: Sequence[str]) -> list[list[float]]:
    return [_embedding(0)]


async def test_retrieve_returns_nearest_ready_chunks_and_non_phi_audit(
    db_session: AsyncSession,
) -> None:
    treatment_id = uuid4()
    ready_document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/anticoagulation.pdf",
        title="Anticoagulation Protocol",
        mime="application/pdf",
        status="ready",
    )
    ignored_document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/draft.pdf",
        title="Draft Protocol",
        mime="application/pdf",
        status="ingesting",
    )
    db_session.add_all([ready_document, ignored_document])
    await db_session.flush()
    db_session.add_all(
        [
            KnowledgeChunk(
                document_id=ready_document.id,
                ordinal=0,
                content="Warfarin requires INR checks within the first week.",
                embedding=_vector_literal(_embedding(0)),
                tokens=9,
            ),
            KnowledgeChunk(
                document_id=ready_document.id,
                ordinal=1,
                content="Metformin counselling covers gastrointestinal effects.",
                embedding=_vector_literal(_embedding(1)),
                tokens=7,
            ),
            KnowledgeChunk(
                document_id=ignored_document.id,
                ordinal=0,
                content="This chunk is not ready and must not be returned.",
                embedding=_vector_literal(_embedding(0)),
                tokens=10,
            ),
        ]
    )
    await db_session.flush()

    citations = await retrieve(
        db_session,
        "warfarin monitoring",
        embedder=_embed_query,
        k=2,
        treatment_id=treatment_id,
    )

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "kb_retrieval_completed")
    )

    assert [citation.text for citation in citations] == [
        "Warfarin requires INR checks within the first week.",
        "Metformin counselling covers gastrointestinal effects.",
    ]
    assert citations[0].score > citations[1].score
    assert citations[0].document_id == ready_document.id
    assert citations[0].document_title == "Anticoagulation Protocol"
    assert citations[0].source_uri == "local://kb/anticoagulation.pdf"
    assert audit is not None
    assert audit.resource_type == "kb_retrieval"
    assert audit.resource_id == treatment_id
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "chunk_count": 2,
        "top_score": citations[0].score,
    }


async def test_retrieve_can_rerank_a_wider_candidate_set(
    db_session: AsyncSession,
) -> None:
    document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/diabetes.pdf",
        title="Diabetes Protocol",
        mime="application/pdf",
        status="ready",
    )
    db_session.add(document)
    await db_session.flush()
    db_session.add_all(
        [
            KnowledgeChunk(
                document_id=document.id,
                ordinal=0,
                content="General diabetes counselling information.",
                embedding=_vector_literal(_embedding(0)),
                tokens=5,
            ),
            KnowledgeChunk(
                document_id=document.id,
                ordinal=1,
                content="Metformin may cause gastrointestinal side effects.",
                embedding=_vector_literal(_embedding(1)),
                tokens=7,
            ),
            KnowledgeChunk(
                document_id=document.id,
                ordinal=2,
                content="Patients on metformin should report severe diarrhoea.",
                embedding=_vector_literal(_embedding(2)),
                tokens=8,
            ),
        ]
    )
    await db_session.flush()

    async def _rerank(
        query: str,
        candidates: Sequence[Citation],
        limit: int,
    ) -> RerankResult:
        assert query == "metformin diarrhoea"
        assert limit == 2
        assert len(candidates) == 3
        return RerankResult(
            citations=[
                RerankedCitation(chunk_id=candidates[2].chunk_id, relevance_score=0.97),
                RerankedCitation(chunk_id=candidates[1].chunk_id, relevance_score=0.81),
            ]
        )

    citations = await retrieve(
        db_session,
        "metformin diarrhoea",
        embedder=_embed_query,
        k=2,
        candidate_k=3,
        reranker=_rerank,
    )

    assert [citation.text for citation in citations] == [
        "Patients on metformin should report severe diarrhoea.",
        "Metformin may cause gastrointestinal side effects.",
    ]
    assert [citation.score for citation in citations] == [0.97, 0.81]


async def test_retrieve_rejects_empty_query_without_embedding(
    db_session: AsyncSession,
) -> None:
    async def _should_not_embed(_texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("empty queries should not call the embedder")

    citations = await retrieve(db_session, "  ", embedder=_should_not_embed)

    assert citations == []
