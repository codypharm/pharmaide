"""Knowledge-base semantic retrieval.

The retrieval path is intentionally small: callers inject an embedder, this
module ranks ready KB chunks by vector distance, and audit/log events record
only metadata. Queries and excerpts may contain clinical context, so they stay
out of audit payloads and structured logs.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EMBEDDING_DIMENSIONS, AuditLogEntry

EmbeddingVector = list[float]
Embedder = Callable[[Sequence[str]], Awaitable[list[EmbeddingVector]]]

log = structlog.get_logger(__name__)
SYSTEM_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")

_RETRIEVAL_SQL = text(
    """
    SELECT
        c.id AS chunk_id,
        c.document_id AS document_id,
        d.title AS document_title,
        d.source_uri AS source_uri,
        c.content AS text,
        c.embedding <=> CAST(:query_vector AS vector(3072)) AS distance
    FROM kb_chunks c
    JOIN kb_documents d ON d.id = c.document_id
    WHERE d.status = 'ready'
    ORDER BY c.embedding <=> CAST(:query_vector AS vector(3072)), c.created_at, c.id
    LIMIT :limit
    """
)


@dataclass(frozen=True)
class Citation:
    """A retrieved KB chunk that can be cited by the analysis graph."""

    chunk_id: UUID
    document_id: UUID
    document_title: str
    source_uri: str
    text: str
    score: float


async def retrieve(
    session: AsyncSession,
    query: str,
    *,
    embedder: Embedder,
    k: int = 5,
    treatment_id: UUID | None = None,
) -> list[Citation]:
    """Return the top-K ready KB chunks for a clinical query."""
    normalized_query = query.strip()
    if not normalized_query:
        return []

    limit = _normalize_limit(k)
    query_embedding = await _embed_query(normalized_query, embedder)
    citations = await _query_citations(session, query_embedding, limit)
    await _audit_retrieval(session, citations, treatment_id=treatment_id)
    log.info(
        "kb_retrieval_completed",
        chunk_count=len(citations),
        top_score=citations[0].score if citations else None,
        treatment_id=str(treatment_id) if treatment_id else None,
    )
    return citations


async def _embed_query(query: str, embedder: Embedder) -> EmbeddingVector:
    embeddings = await embedder([query])
    if len(embeddings) != 1:
        raise ValueError("query embedder must return exactly one embedding")
    if len(embeddings[0]) != EMBEDDING_DIMENSIONS:
        raise ValueError("query embedding dimension mismatch")
    return embeddings[0]


def _normalize_limit(k: int) -> int:
    if k < 1:
        raise ValueError("retrieval limit must be positive")
    return k


async def _query_citations(
    session: AsyncSession,
    query_embedding: Sequence[float],
    limit: int,
) -> list[Citation]:
    result = await session.execute(
        _RETRIEVAL_SQL,
        {
            "query_vector": _vector_literal(query_embedding),
            "limit": limit,
        },
    )
    return [
        Citation(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            document_title=row.document_title,
            source_uri=row.source_uri,
            text=row.text,
            score=_score_from_distance(row.distance),
        )
        for row in result
    ]


async def _audit_retrieval(
    session: AsyncSession,
    citations: Sequence[Citation],
    *,
    treatment_id: UUID | None,
) -> None:
    top_score = citations[0].score if citations else None
    payload: dict[str, object] = {
        "chunk_count": len(citations),
        "top_score": top_score,
    }
    if treatment_id is not None:
        payload["treatment_id"] = str(treatment_id)

    session.add(
        AuditLogEntry(
            event_type="kb_retrieval_completed",
            resource_type="kb_retrieval",
            resource_id=treatment_id or SYSTEM_RESOURCE_ID,
            payload=payload,
        )
    )
    await session.flush()


def _score_from_distance(distance: float) -> float:
    # pgvector cosine distance is 0 for identical vectors and larger as
    # relevance drops. Clamp defensively for floating-point edge cases.
    return max(0.0, min(1.0, 1.0 - float(distance)))


def _vector_literal(embedding: Sequence[float]) -> str:
    """Render a pgvector literal; never log the vector contents."""
    return f"[{','.join(str(value) for value in embedding)}]"
