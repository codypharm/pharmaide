"""Deterministic RAG chunking and retrieval quality evaluation.

This eval uses real product rows from ``test-data/products.csv`` while keeping
embeddings deterministic. It measures whether ingestion preserves CSV context
and whether retrieval finds relevant product rows ahead of distractors.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
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
BACKEND_ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_CSV = Path(__file__).resolve().parents[3] / "test-data" / "products.csv"
REPORT_DIR = BACKEND_ROOT / ".reports"
REPORT_JSON = REPORT_DIR / "rag-eval-report.json"
REPORT_HTML = REPORT_DIR / "rag-eval-report.html"
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
    query: str
    expected_names: tuple[str, ...]
    retrieved: tuple["RetrievedCitation", ...]
    matches: list[bool]
    expected_count: int


@dataclass(frozen=True)
class RetrievedCitation:
    rank: int
    name: str
    relevant: bool
    score: float
    document_title: str
    source_uri: str


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
    summary = _metrics_summary(results)
    _write_rag_eval_report(results, summary)

    assert summary["hit_rate_at_3"] >= MIN_HIT_RATE_AT_3
    assert summary["mrr"] >= MIN_MRR
    assert summary["precision_at_3"] >= MIN_PRECISION_AT_3
    assert summary["recall_at_3"] >= MIN_RECALL_AT_3


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
    retrieved = tuple(
        RetrievedCitation(
            rank=index,
            name=_name_from_chunk(citation.text),
            relevant=_citation_matches(citation, gold_query.expected_names),
            score=citation.score,
            document_title=citation.document_title,
            source_uri=citation.source_uri,
        )
        for index, citation in enumerate(citations, start=1)
    )
    return QueryEvalResult(
        query=gold_query.query,
        expected_names=tuple(sorted(gold_query.expected_names)),
        retrieved=retrieved,
        matches=[citation.relevant for citation in retrieved],
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
    return (
        sum(
            min(sum(result.matches), result.expected_count) / result.expected_count
            for result in results
        )
        / len(results)
    )


def _metrics_summary(results: Sequence[QueryEvalResult]) -> dict[str, float]:
    return {
        "hit_rate_at_3": round(_hit_rate(results), 4),
        "mrr": round(_mean_reciprocal_rank(results), 4),
        "precision_at_3": round(_mean_precision(results), 4),
        "recall_at_3": round(_mean_recall(results), 4),
    }


def _write_rag_eval_report(
    results: Sequence[QueryEvalResult],
    summary: dict[str, float],
) -> None:
    """Write local artifacts for reviewing RAG quality across eval runs."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = _report_payload(results, summary)
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    REPORT_HTML.write_text(_render_html_report(payload), encoding="utf-8")


def _report_payload(
    results: Sequence[QueryEvalResult],
    summary: dict[str, float],
) -> dict[str, object]:
    return {
        "dataset": "test-data/products.csv",
        "mode": "deterministic",
        "k": TOP_K,
        "thresholds": {
            "hit_rate_at_3": MIN_HIT_RATE_AT_3,
            "mrr": MIN_MRR,
            "precision_at_3": MIN_PRECISION_AT_3,
            "recall_at_3": MIN_RECALL_AT_3,
        },
        "summary": summary,
        "queries": [
            {
                "query": result.query,
                "expected": list(result.expected_names),
                "retrieved": [
                    {
                        "rank": citation.rank,
                        "name": citation.name,
                        "relevant": citation.relevant,
                        "score": round(citation.score, 4),
                        "document_title": citation.document_title,
                        "source_uri": citation.source_uri,
                    }
                    for citation in result.retrieved
                ],
            }
            for result in results
        ],
    }


def _render_html_report(payload: dict[str, object]) -> str:
    summary = payload["summary"]
    assert isinstance(summary, dict)
    queries = payload["queries"]
    assert isinstance(queries, list)
    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "<head>",
            "  <meta charset=\"utf-8\">",
            "  <title>PharmaAide RAG Evaluation Report</title>",
            "  <style>",
            _report_css(),
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <header>",
            "      <p class=\"eyebrow\">RAG Evaluation</p>",
            "      <h1>Products retrieval quality</h1>",
            f"      <p>{escape(str(payload['dataset']))} · {escape(str(payload['mode']))}</p>",
            "    </header>",
            f"    {_summary_cards(summary)}",
            f"    {_summary_bar_chart(summary)}",
            f"    {_query_relevance_chart(queries)}",
            f"    {_query_tables(queries)}",
            "  </main>",
            "</body>",
            "</html>",
        ]
    )


def _summary_cards(summary: dict[object, object]) -> str:
    cards = []
    for label, value in summary.items():
        cards.append(
            "<section class=\"metric\">"
            f"<span>{escape(str(label).replace('_', ' ').title())}</span>"
            f"<strong>{escape(str(value))}</strong>"
            "</section>"
        )
    return f"<div class=\"metrics\">{''.join(cards)}</div>"


def _summary_bar_chart(summary: dict[object, object]) -> str:
    bars = []
    for label, raw_value in summary.items():
        value = float(raw_value)
        width = max(0.0, min(100.0, value * 100))
        bars.append(
            "<div class=\"bar-row\">"
            f"<span>{escape(str(label).replace('_', ' ').title())}</span>"
            "<div class=\"bar-track\">"
            f"<div class=\"bar-fill\" style=\"width: {width:.1f}%\"></div>"
            "</div>"
            f"<strong>{value:.4g}</strong>"
            "</div>"
        )
    return (
        "<section class=\"chart\">"
        "<h2>Summary metrics</h2>"
        f"{''.join(bars)}"
        "</section>"
    )


def _query_relevance_chart(queries: list[object]) -> str:
    rows = []
    for query in queries:
        assert isinstance(query, dict)
        retrieved = query["retrieved"]
        assert isinstance(retrieved, list)
        relevant_count = sum(1 for row in retrieved if isinstance(row, dict) and row["relevant"])
        width = relevant_count / TOP_K * 100
        rows.append(
            "<div class=\"bar-row\">"
            f"<span>{escape(str(query['query']))}</span>"
            "<div class=\"bar-track\">"
            f"<div class=\"bar-fill\" style=\"width: {width:.1f}%\"></div>"
            "</div>"
            f"<strong>{relevant_count}/{TOP_K}</strong>"
            "</div>"
        )
    return (
        "<section class=\"chart\">"
        "<h2>Relevant results in top 3</h2>"
        f"{''.join(rows)}"
        "</section>"
    )


def _query_tables(queries: list[object]) -> str:
    sections: list[str] = []
    for query in queries:
        assert isinstance(query, dict)
        expected = ", ".join(str(value) for value in query["expected"])
        retrieved = query["retrieved"]
        assert isinstance(retrieved, list)
        rows = "".join(_retrieved_row(row) for row in retrieved)
        sections.append(
            "<section class=\"query\">"
            f"<h2>{escape(str(query['query']))}</h2>"
            f"<p><strong>Expected:</strong> {escape(expected)}</p>"
            "<table>"
            "<thead><tr><th>Rank</th><th>Relevant</th><th>Score</th><th>Name</th></tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table>"
            "</section>"
        )
    return "".join(sections)


def _retrieved_row(row: object) -> str:
    assert isinstance(row, dict)
    relevant = "yes" if row["relevant"] else "no"
    class_name = "hit" if row["relevant"] else "miss"
    return (
        f"<tr class=\"{class_name}\">"
        f"<td>{escape(str(row['rank']))}</td>"
        f"<td>{escape(relevant)}</td>"
        f"<td>{escape(str(row['score']))}</td>"
        f"<td>{escape(str(row['name']))}</td>"
        "</tr>"
    )


def _report_css() -> str:
    return "\n".join(
        [
            "body { margin: 0; background: #f8f9ff; color: #111827; "
            "font-family: Public Sans, Arial, sans-serif; }",
            "main { max-width: 1180px; margin: 0 auto; padding: 32px; }",
            "header, .metric, .query, .chart { background: #fff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; }",
            "header { padding: 24px; margin-bottom: 16px; }",
            "h1, h2, p { margin: 0; }",
            "h1 { font-size: 28px; margin-top: 8px; }",
            "h2 { font-size: 18px; margin-bottom: 8px; }",
            ".eyebrow { color: #64748b; font-size: 11px; font-weight: 700; "
            "letter-spacing: .05em; text-transform: uppercase; }",
            ".metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); "
            "gap: 12px; margin-bottom: 16px; }",
            ".metric { padding: 16px; }",
            ".metric span { display: block; color: #64748b; font-size: 11px; "
            "font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }",
            ".metric strong { display: block; font-size: 30px; margin-top: 8px; }",
            ".chart { padding: 18px; margin-bottom: 16px; }",
            ".bar-row { display: grid; grid-template-columns: 260px 1fr 70px; "
            "gap: 12px; align-items: center; margin-top: 12px; }",
            ".bar-row span { color: #334155; overflow-wrap: anywhere; }",
            ".bar-row strong { font-variant-numeric: tabular-nums; text-align: right; }",
            ".bar-track { height: 18px; background: #eef2f7; border: 1px solid #e2e8f0; "
            "border-radius: 4px; overflow: hidden; }",
            ".bar-fill { height: 100%; background: #131b2e; }",
            ".query { padding: 18px; margin-bottom: 12px; overflow: hidden; }",
            "table { width: 100%; border-collapse: collapse; margin-top: 12px; "
            "table-layout: fixed; }",
            "th, td { border-top: 1px solid #e2e8f0; padding: 10px; text-align: left; "
            "vertical-align: top; overflow-wrap: anywhere; }",
            "th { color: #64748b; font-size: 11px; font-weight: 700; "
            "letter-spacing: .05em; text-transform: uppercase; background: #f8fafc; }",
            ".hit td:nth-child(2) { color: #047857; font-weight: 700; }",
            ".miss td:nth-child(2) { color: #b91c1c; font-weight: 700; }",
            "@media (max-width: 800px) { .metrics { grid-template-columns: 1fr 1fr; } "
            ".bar-row { grid-template-columns: 1fr; } main { padding: 16px; } }",
        ]
    )


def _product_name(segment: TextSegment) -> str:
    return _name_from_chunk(segment.content)


def _name_from_chunk(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("name: "):
            return line.removeprefix("name: ")
    return ""


def _vector_literal(embedding: Sequence[float]) -> str:
    return f"[{','.join(str(value) for value in embedding)}]"
