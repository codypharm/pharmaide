"""Deterministic RAG chunking and retrieval quality evaluation.

This eval uses real product rows from ``test-data/products.csv`` while keeping
embeddings deterministic. It measures whether ingestion preserves CSV context
and whether retrieval finds relevant product rows ahead of distractors.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EMBEDDING_DIMENSIONS, AuditLogEntry, KnowledgeChunk, KnowledgeDocument
from app.services.chunker import chunk_segments
from app.services.kb_parsers.csv import parse_csv_segments
from app.services.kb_retrieval import Citation, retrieve
from app.services.kb_segments import TextSegment

pytestmark = [pytest.mark.clinical_eval, pytest.mark.usefixtures("postgres_container")]

SCOPE_ID = UUID("11111111-1111-4111-8111-111111111111")
PRODUCTS_CSV = Path(__file__).resolve().parents[3] / "test-data" / "products.csv"
TOP_K = 3
MIN_HIT_RATE_AT_3 = 1.0
MIN_MRR = 0.8
MIN_PRECISION_AT_3 = 0.5
MIN_RECALL_AT_3 = 0.8


@dataclass(frozen=True)
class GoldQuery:
    query: str
    expected_names: frozenset[str]


@dataclass(frozen=True)
class QueryEvalResult:
    matches: list[bool]
    expected_count: int


GOLD_QUERIES = [
    GoldQuery(
        query="metronidazole flagyl",
        expected_names=frozenset(
            {
                "Flagyl 500mg Metronidazole",
                "Flagyl 125mg/5ml Metronidazole Pediatric Intestinal Antiseptic Suspension",
            }
        ),
    ),
    GoldQuery(
        query="amoxicillin clavulanic acid augmentin",
        expected_names=frozenset(
            {
                "Augmentin 875mg Amoxicillin & 125mg Clavulanic Acid",
                "Augmentin 500mg Amoxycillin & 125mg Clavulanic Acid",
                "Augmentin 400mg/5ml Amoxicillin & 57mg/5ml Clavulanic Acid "
                "Oral Suspension Powder Mixed Fruits Flavor",
            }
        ),
    ),
    GoldQuery(
        query="paracetamol pain fever relief",
        expected_names=frozenset(
            {
                "Doliprane 1000mg Paracetamol for Pain Relief & Fever",
                "Doliprane 1000mg Paracetamol Pain & Fever Treatment",
                "Panadol Advance 500mg Paracetamol for Pain & Fever Relief",
            }
        ),
    ),
    GoldQuery(
        query="fexofenadine telfast antihistamine",
        expected_names=frozenset(
            {
                "Telfast 180mg Fexofenadine HCl Antihistamine",
                "Telfast 120mg Fexofenadine HCI Non-Drowsy Antihistamine",
            }
        ),
    ),
    GoldQuery(
        query="ibuprofen brufen children syrup",
        expected_names=frozenset(
            {
                "Brufen 100mg/5ml Ibuprofen Syrup Orange Flavor for Children (3+ Months)",
                "Brufen 400mg Ibuprofen",
                "Brufen 600mg Ibuprofen for Reducing Fever, Relieving Pain & "
                "Treating Inflammations",
            }
        ),
    ),
    GoldQuery(
        query="xylometazoline otrivin nasal drops child adult",
        expected_names=frozenset(
            {
                "Otrivin Child 0.05% Xylometazoline HCL Nasal Drops (1-11 Years)",
                "Otrivin 0.1% Xylometazoline HCL Moisturizing Nasal Drops for Adults",
            }
        ),
    ),
    GoldQuery(
        query="pantoprazole controloc gastro resistant",
        expected_names=frozenset(
            {
                "Controloc 40mg Pantoprazole Sodium Sesquihydrate Gastro-Resistant",
                "Controloc 20mg Pantoprazole Sodium Sesquihydrate",
                "Controloc 42.3mg Pantoprazole Sodium Powder Vial for Intravenous "
                "Injection Solution",
            }
        ),
    ),
    GoldQuery(
        query="cerave hydrating cleanser normal dry skin",
        expected_names=frozenset(
            {
                "CeraVe Hypoallergenic Hydrating Face & Body Cleanser with Ceramides "
                "& Hyaluronic Acid for Normal to Dry Skin - fragrance free",
            }
        ),
    ),
]

SELECTED_PRODUCT_NAMES = frozenset(
    {
        *set().union(*(query.expected_names for query in GOLD_QUERIES)),
        "La Roche-Posay Retinol B3 Anti-Aging Facial Serum",
        "Centrum Multivitamin & Multimineral Supplement with Lutein for Adults",
        "Disposable 3ml Syringe for Adults",
        "Baby Check Super Sensitive One Step Pregnancy Test",
        "NAN Optipro Growing Up Milk Formula with 2-FL & BL Probiotic Stage 3 (1-3 Years)",
        "Hairtonic Supplement with Biotin",
        "Tiger Pain Relief Plaster",
        "Omega-3 Plus 1000mg Fish Oil Supplement with Wheatgerm Oil",
    }
)

FEATURE_AXES = {
    "metronidazole": 0,
    "flagyl": 1,
    "amoxicillin": 2,
    "amoxycillin": 2,
    "clavulanic": 3,
    "augmentin": 4,
    "paracetamol": 5,
    "panadol": 6,
    "doliprane": 7,
    "pain": 8,
    "fever": 9,
    "fexofenadine": 10,
    "telfast": 11,
    "antihistamine": 12,
    "ibuprofen": 13,
    "brufen": 14,
    "children": 15,
    "syrup": 16,
    "xylometazoline": 17,
    "otrivin": 18,
    "nasal": 19,
    "drops": 20,
    "child": 21,
    "adult": 22,
    "adults": 22,
    "pantoprazole": 23,
    "controloc": 24,
    "gastro": 25,
    "resistant": 26,
    "cerave": 27,
    "hydrating": 28,
    "cleanser": 29,
    "normal": 30,
    "dry": 31,
    "skin": 32,
}


async def test_rag_eval_retrieves_relevant_product_chunks_with_ir_metrics(
    db_session: AsyncSession,
) -> None:
    await _persist_product_chunks(db_session)

    results = [
        await _evaluate_query(db_session, gold_query)
        for gold_query in GOLD_QUERIES
    ]

    assert _hit_rate(results) >= MIN_HIT_RATE_AT_3
    assert _mean_reciprocal_rank(results) >= MIN_MRR
    assert _mean_precision(results) >= MIN_PRECISION_AT_3
    assert _mean_recall(results) >= MIN_RECALL_AT_3


async def test_rag_eval_preserves_csv_context_in_retrieved_chunks(
    db_session: AsyncSession,
) -> None:
    await _persist_product_chunks(db_session)

    citations = await retrieve(
        db_session,
        "flagyl metronidazole",
        embedder=_embed_query,
        k=TOP_K,
        uploaded_by=SCOPE_ID,
    )

    assert citations
    for citation in citations:
        assert "Document: products.csv" in citation.text
        assert "Row:" in citation.text
        assert "name:" in citation.text
        assert "packaging:" in citation.text
        assert "price:" in citation.text
        assert "discounted_price:" in citation.text


async def test_rag_eval_audits_retrieval_without_query_or_product_text(
    db_session: AsyncSession,
) -> None:
    await _persist_product_chunks(db_session)
    query = "flagyl metronidazole"

    await retrieve(
        db_session,
        query,
        embedder=_embed_query,
        k=TOP_K,
        treatment_id=UUID("33333333-3333-4333-8333-333333333333"),
        uploaded_by=SCOPE_ID,
    )

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "kb_retrieval_completed")
    )
    assert audit is not None
    serialized_payload = str(audit.payload).lower()
    assert "chunk_count" in audit.payload
    assert "top_score" in audit.payload
    assert query not in serialized_payload
    assert "flagyl" not in serialized_payload
    assert "metronidazole" not in serialized_payload


async def _persist_product_chunks(session: AsyncSession) -> None:
    document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://eval/products.csv",
        title="products.csv",
        mime="text/csv",
        status="ready",
        uploaded_by=SCOPE_ID,
    )
    session.add(document)
    await session.flush()

    selected_segments = _selected_product_segments()
    chunks = chunk_segments(selected_segments, max_tokens=120, overlap_tokens=20)
    session.add_all(
        [
            KnowledgeChunk(
                document_id=document.id,
                ordinal=index,
                content=chunk.content,
                embedding=_vector_literal(_embedding_for_text(chunk.content)),
                tokens=chunk.tokens,
            )
            for index, chunk in enumerate(chunks)
        ]
    )
    await session.flush()


def _selected_product_segments() -> list[TextSegment]:
    segments = parse_csv_segments(PRODUCTS_CSV.read_bytes(), title="products.csv")
    selected = [
        segment
        for segment in segments
        if _product_name(segment) in SELECTED_PRODUCT_NAMES
    ]
    missing = SELECTED_PRODUCT_NAMES - {_product_name(segment) for segment in selected}
    assert not missing, f"products.csv fixture missing selected rows: {sorted(missing)}"
    return selected


async def _evaluate_query(
    session: AsyncSession,
    gold_query: GoldQuery,
) -> QueryEvalResult:
    citations = await retrieve(
        session,
        gold_query.query,
        embedder=_embed_query,
        k=TOP_K,
        uploaded_by=SCOPE_ID,
    )
    return QueryEvalResult(
        matches=[_citation_matches(citation, gold_query.expected_names) for citation in citations],
        expected_count=min(TOP_K, len(gold_query.expected_names)),
    )


async def _embed_query(texts: Sequence[str]) -> list[list[float]]:
    return [_embedding_for_text(text) for text in texts]


def _embedding_for_text(text: str) -> list[float]:
    lower = text.lower()
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token, axis in FEATURE_AXES.items():
        if token in lower:
            vector[axis] += 1.0
    # Keep every vector non-zero for cosine distance while preserving feature dominance.
    vector[-1] = 0.01
    return vector


def _citation_matches(citation: Citation, expected_names: frozenset[str]) -> bool:
    name = _name_from_chunk(citation.text)
    return name in expected_names


def _hit_rate(results: Sequence[QueryEvalResult]) -> float:
    return sum(any(result.matches) for result in results) / len(results)


def _mean_reciprocal_rank(results: Sequence[QueryEvalResult]) -> float:
    return sum(_reciprocal_rank(result.matches) for result in results) / len(results)


def _reciprocal_rank(matches: Sequence[bool]) -> float:
    for index, matched in enumerate(matches, start=1):
        if matched:
            return 1 / index
    return 0


def _mean_precision(results: Sequence[QueryEvalResult]) -> float:
    return sum(sum(result.matches) / TOP_K for result in results) / len(results)


def _mean_recall(results: Sequence[QueryEvalResult]) -> float:
    return sum(sum(result.matches) / result.expected_count for result in results) / len(results)


def _product_name(segment: TextSegment) -> str:
    return _name_from_chunk(segment.content)


def _name_from_chunk(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("name: "):
            return line.removeprefix("name: ")
    return ""


def _vector_literal(embedding: Sequence[float]) -> str:
    return f"[{','.join(str(value) for value in embedding)}]"
