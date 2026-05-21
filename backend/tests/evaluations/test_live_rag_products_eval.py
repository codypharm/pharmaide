"""Manual live RAG retrieval evaluation for an ingested products.csv document.

This eval does not re-embed the uploaded product chunks. It finds an existing
ready ``products.csv`` knowledge document in the configured database, embeds a
large batch of generated product queries, and measures retrieval quality against
the already-stored vectors.
"""

import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path

import pytest
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import Settings
from app.db.models import KnowledgeChunk, KnowledgeDocument
from app.services.embeddings import build_embedding_client, embed_texts
from app.services.kb_parsers.csv import parse_csv_segments
from app.services.kb_retrieval import retrieve
from app.services.kb_segments import TextSegment

pytestmark = [
    pytest.mark.clinical_eval,
    pytest.mark.live_embedding,
    pytest.mark.skipif(
        os.getenv("PHARMAIDE_RUN_LIVE_RAG_EVAL") != "1",
        reason="Set PHARMAIDE_RUN_LIVE_RAG_EVAL=1 to run the manual live RAG eval.",
    ),
]

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_CSV = Path(__file__).resolve().parents[3] / "test-data" / "products.csv"
REPORT_DIR = BACKEND_ROOT / ".reports"
REPORT_JSON = REPORT_DIR / "rag-live-products-report.json"
REPORT_HTML = REPORT_DIR / "rag-live-products-report.html"
TOP_K = 5
DEFAULT_QUERY_LIMIT = 100
DEFAULT_MIN_HIT_RATE_AT_5 = 0.6
DEFAULT_MIN_MRR = 0.4
DEFAULT_MIN_PRECISION_AT_5 = 0.12
DEFAULT_MIN_RECALL_AT_5 = 0.6

STOPWORDS = {
    "and",
    "anti",
    "body",
    "effective",
    "flavor",
    "for",
    "free",
    "from",
    "hcl",
    "hci",
    "mg",
    "ml",
    "non",
    "oral",
    "pack",
    "per",
    "plus",
    "relief",
    "sensitive",
    "skin",
    "tablets",
    "the",
    "with",
    "years",
}


@dataclass(frozen=True)
class GoldQuery:
    query: str
    expected_name: str
    relevant_names: frozenset[str]


@dataclass(frozen=True)
class LiveQueryResult:
    query: str
    expected_name: str
    relevant_names: tuple[str, ...]
    retrieved: tuple["LiveRetrievedCitation", ...]

    @property
    def first_exact_rank(self) -> int | None:
        for citation in self.retrieved:
            if citation.exact_match:
                return citation.rank
        return None

    @property
    def first_related_rank(self) -> int | None:
        for citation in self.retrieved:
            if citation.related_match:
                return citation.rank
        return None


@dataclass(frozen=True)
class LiveRetrievedCitation:
    rank: int
    name: str
    exact_match: bool
    related_match: bool
    score: float
    document_title: str
    source_uri: str


@pytest.mark.skipif(
    os.getenv("PHARMAIDE_RUN_LIVE_RAG_EVAL") != "1",
    reason="Set PHARMAIDE_RUN_LIVE_RAG_EVAL=1 to run the manual live RAG eval.",
)
async def test_live_products_rag_eval_uses_existing_ingested_vectors() -> None:
    settings = Settings()
    if settings.openai_api_key is None:
        pytest.skip("PHARMAIDE_OPENAI_API_KEY is required for live query embeddings.")

    query_limit = _live_query_limit()
    gold_queries = _generated_gold_queries(query_limit)
    engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
    client = build_embedding_client(settings.openai_api_key)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                document, chunk_count = await _find_ready_products_document(session)
                query_vectors = await embed_texts(
                    [query.query for query in gold_queries],
                    client=client,
                )
                embedder = _cached_query_embedder(gold_queries, query_vectors)
                results = [
                    await _evaluate_live_query(session, query, embedder, document.uploaded_by)
                    for query in gold_queries
                ]
                summary = _live_metrics_summary(results, chunk_count=chunk_count)
                _write_live_report(results, summary)

                assert summary["hit_rate_at_5"] >= _threshold(
                    "PHARMAIDE_LIVE_RAG_MIN_HIT_RATE_AT_5",
                    DEFAULT_MIN_HIT_RATE_AT_5,
                )
                assert summary["mrr"] >= _threshold("PHARMAIDE_LIVE_RAG_MIN_MRR", DEFAULT_MIN_MRR)
                assert summary["precision_at_5"] >= _threshold(
                    "PHARMAIDE_LIVE_RAG_MIN_PRECISION_AT_5",
                    DEFAULT_MIN_PRECISION_AT_5,
                )
                assert summary["recall_at_5"] >= _threshold(
                    "PHARMAIDE_LIVE_RAG_MIN_RECALL_AT_5",
                    DEFAULT_MIN_RECALL_AT_5,
                )
            finally:
                await session.close()
                if transaction.is_active:
                    await transaction.rollback()
    finally:
        await client.close()
        await engine.dispose()


async def _find_ready_products_document(
    session: AsyncSession,
) -> tuple[KnowledgeDocument, int]:
    documents = (
        await session.execute(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.source_type == "user_upload",
                KnowledgeDocument.status == "ready",
                or_(
                    KnowledgeDocument.title.ilike("%products.csv%"),
                    KnowledgeDocument.source_uri.ilike("%products.csv%"),
                ),
                KnowledgeDocument.uploaded_by.is_not(None),
            )
            .order_by(KnowledgeDocument.updated_at.desc())
        )
    ).scalars()

    for document in documents:
        chunk_count = await session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document.id)
        )
        if chunk_count:
            return document, int(chunk_count)

    pytest.skip("No ready ingested products.csv knowledge document with chunks was found.")


async def _evaluate_live_query(
    session: AsyncSession,
    gold_query: GoldQuery,
    embedder,
    uploaded_by,
) -> LiveQueryResult:
    citations = await retrieve(
        session,
        gold_query.query,
        embedder=embedder,
        k=TOP_K,
        uploaded_by=uploaded_by,
    )
    retrieved = tuple(
        LiveRetrievedCitation(
            rank=index,
            name=_name_from_chunk(citation.text),
            exact_match=_name_from_chunk(citation.text) == gold_query.expected_name,
            related_match=_name_from_chunk(citation.text) in gold_query.relevant_names,
            score=citation.score,
            document_title=citation.document_title,
            source_uri=citation.source_uri,
        )
        for index, citation in enumerate(citations, start=1)
    )
    return LiveQueryResult(
        query=gold_query.query,
        expected_name=gold_query.expected_name,
        relevant_names=tuple(sorted(gold_query.relevant_names)),
        retrieved=retrieved,
    )


def _cached_query_embedder(
    queries: Sequence[GoldQuery],
    vectors: Sequence[list[float]],
):
    cache = {query.query: vector for query, vector in zip(queries, vectors, strict=True)}

    async def embedder(texts: Sequence[str]) -> list[list[float]]:
        return [cache[text] for text in texts]

    return embedder


def _generated_gold_queries(limit: int) -> list[GoldQuery]:
    segments = parse_csv_segments(PRODUCTS_CSV.read_bytes(), title="products.csv")
    product_names = [_product_name(segment) for segment in segments if _product_name(segment)]
    related_names_by_product = _related_names_by_product(product_names)
    queries: list[GoldQuery] = []
    seen_names: set[str] = set()
    for segment in segments:
        name = _product_name(segment)
        if not name or name in seen_names:
            continue
        query = _query_from_product_name(name)
        if len(query.split()) < 3:
            continue
        queries.append(
            GoldQuery(
                query=query,
                expected_name=name,
                relevant_names=related_names_by_product[name],
            )
        )
        seen_names.add(name)
        if len(queries) >= limit:
            return queries
    return queries


def _query_from_product_name(name: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    selected = [
        token
        for token in tokens
        if token not in STOPWORDS and (len(token) > 2 or any(char.isdigit() for char in token))
    ]
    return " ".join(selected[:8]) or name


def _related_names_by_product(product_names: Sequence[str]) -> dict[str, frozenset[str]]:
    token_sets = {name: _relevance_tokens(name) for name in product_names}
    return {
        name: frozenset(
            candidate
            for candidate, candidate_tokens in token_sets.items()
            if _products_are_related(tokens, candidate_tokens)
        )
        for name, tokens in token_sets.items()
    }


def _relevance_tokens(name: str) -> frozenset[str]:
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    return frozenset(
        token
        for token in tokens
        if token not in STOPWORDS and (len(token) > 2 or any(char.isdigit() for char in token))
    )


def _products_are_related(
    left: frozenset[str],
    right: frozenset[str],
) -> bool:
    shared = left & right
    if len(shared) >= 2:
        return True
    return len(shared) == 1 and any(any(char.isdigit() for char in token) for token in shared)


def _live_metrics_summary(
    results: Sequence[LiveQueryResult],
    *,
    chunk_count: int,
) -> dict[str, float | int]:
    return {
        "query_count": len(results),
        "chunk_count": chunk_count,
        "hit_rate_at_5": round(_exact_hit_rate(results), 4),
        "related_hit_rate_at_5": round(_related_hit_rate(results), 4),
        "mrr": round(_mean_reciprocal_rank(results), 4),
        "precision_at_5": round(_mean_precision(results), 4),
        "recall_at_5": round(_mean_recall(results), 4),
    }


def _exact_hit_rate(results: Sequence[LiveQueryResult]) -> float:
    return sum(result.first_exact_rank is not None for result in results) / len(results)


def _related_hit_rate(results: Sequence[LiveQueryResult]) -> float:
    return sum(result.first_related_rank is not None for result in results) / len(results)


def _mean_reciprocal_rank(results: Sequence[LiveQueryResult]) -> float:
    return sum(_reciprocal_rank(result) for result in results) / len(results)


def _reciprocal_rank(result: LiveQueryResult) -> float:
    if result.first_exact_rank is None:
        return 0
    return 1 / result.first_exact_rank


def _mean_precision(results: Sequence[LiveQueryResult]) -> float:
    return (
        sum(
            sum(citation.related_match for citation in result.retrieved) / TOP_K
            for result in results
        )
        / len(results)
    )


def _mean_recall(results: Sequence[LiveQueryResult]) -> float:
    return (
        sum(
            min(
                sum(citation.related_match for citation in result.retrieved),
                len(result.relevant_names),
            )
            / min(TOP_K, len(result.relevant_names))
            for result in results
        )
        / len(results)
    )


def _write_live_report(
    results: Sequence[LiveQueryResult],
    summary: dict[str, float | int],
) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = _live_report_payload(results, summary)
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    REPORT_HTML.write_text(_render_live_html(payload), encoding="utf-8")


def _live_report_payload(
    results: Sequence[LiveQueryResult],
    summary: dict[str, float | int],
) -> dict[str, object]:
    return {
        "dataset": "existing ingested products.csv",
        "mode": "live_embedding_existing_vectors",
        "k": TOP_K,
        "thresholds": {
            "hit_rate_at_5": _threshold(
                "PHARMAIDE_LIVE_RAG_MIN_HIT_RATE_AT_5",
                DEFAULT_MIN_HIT_RATE_AT_5,
            ),
            "mrr": _threshold("PHARMAIDE_LIVE_RAG_MIN_MRR", DEFAULT_MIN_MRR),
            "precision_at_5": _threshold(
                "PHARMAIDE_LIVE_RAG_MIN_PRECISION_AT_5",
                DEFAULT_MIN_PRECISION_AT_5,
            ),
            "recall_at_5": _threshold(
                "PHARMAIDE_LIVE_RAG_MIN_RECALL_AT_5",
                DEFAULT_MIN_RECALL_AT_5,
            ),
        },
        "summary": summary,
        "rank_distribution": _rank_distribution(results),
        "queries": [
            {
                "query": result.query,
                "expected": result.expected_name,
                "related_expected": list(result.relevant_names),
                "first_exact_rank": result.first_exact_rank,
                "first_related_rank": result.first_related_rank,
                "retrieved": [
                    {
                        "rank": citation.rank,
                        "name": citation.name,
                        "exact_match": citation.exact_match,
                        "related_match": citation.related_match,
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


def _rank_distribution(results: Sequence[LiveQueryResult]) -> dict[str, int]:
    distribution = {str(rank): 0 for rank in range(1, TOP_K + 1)}
    distribution["miss"] = 0
    for result in results:
        rank = result.first_exact_rank
        if rank is None:
            distribution["miss"] += 1
        else:
            distribution[str(rank)] += 1
    return distribution


def _render_live_html(payload: dict[str, object]) -> str:
    summary = payload["summary"]
    rank_distribution = payload["rank_distribution"]
    queries = payload["queries"]
    assert isinstance(summary, dict)
    assert isinstance(rank_distribution, dict)
    assert isinstance(queries, list)
    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "<head>",
            "  <meta charset=\"utf-8\">",
            "  <title>PharmaAide Live RAG Evaluation Report</title>",
            "  <style>",
            _report_css(),
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <header>",
            "      <p class=\"eyebrow\">Live RAG Evaluation</p>",
            "      <h1>Products retrieval quality</h1>",
            f"      <p>{escape(str(payload['dataset']))} · {escape(str(payload['mode']))}</p>",
            "    </header>",
            f"    {_summary_cards(summary)}",
            f"    {_summary_bar_chart(summary)}",
            f"    {_rank_distribution_chart(rank_distribution)}",
            f"    {_query_result_table(queries)}",
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
    metric_keys = [
        "hit_rate_at_5",
        "related_hit_rate_at_5",
        "mrr",
        "precision_at_5",
        "recall_at_5",
    ]
    rows = []
    for key in metric_keys:
        value = float(summary[key])
        rows.append(_bar_row(key.replace("_", " ").title(), value, f"{value:.4g}"))
    return "<section class=\"chart\"><h2>Summary metrics</h2>" + "".join(rows) + "</section>"


def _rank_distribution_chart(rank_distribution: dict[object, object]) -> str:
    total = sum(int(value) for value in rank_distribution.values()) or 1
    rows = []
    for label, value in rank_distribution.items():
        count = int(value)
        rows.append(_bar_row(f"Rank {label}", count / total, str(count)))
    return (
        "<section class=\"chart\">"
        "<h2>First exact result rank</h2>"
        f"{''.join(rows)}"
        "</section>"
    )


def _bar_row(label: str, ratio: float, value_label: str) -> str:
    width = max(0.0, min(100.0, ratio * 100))
    return (
        "<div class=\"bar-row\">"
        f"<span>{escape(label)}</span>"
        "<div class=\"bar-track\">"
        f"<div class=\"bar-fill\" style=\"width: {width:.1f}%\"></div>"
        "</div>"
        f"<strong>{escape(value_label)}</strong>"
        "</div>"
    )


def _query_result_table(queries: list[object]) -> str:
    rows = "".join(_query_row(query) for query in queries)
    return (
        "<section class=\"query\">"
        "<h2>Query results</h2>"
        "<table>"
        "<thead>"
        "<tr><th>Query</th><th>Expected</th><th>Exact Rank</th><th>Related Rank</th>"
        "<th>Top Result</th></tr>"
        "</thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
        "</section>"
    )


def _query_row(query: object) -> str:
    assert isinstance(query, dict)
    retrieved = query["retrieved"]
    assert isinstance(retrieved, list)
    top = retrieved[0] if retrieved else {}
    assert isinstance(top, dict)
    exact_rank = query["first_exact_rank"] or "miss"
    related_rank = query["first_related_rank"] or "miss"
    class_name = "hit" if query["first_exact_rank"] else "miss"
    return (
        f"<tr class=\"{class_name}\">"
        f"<td>{escape(str(query['query']))}</td>"
        f"<td>{escape(str(query['expected']))}</td>"
        f"<td>{escape(str(exact_rank))}</td>"
        f"<td>{escape(str(related_rank))}</td>"
        f"<td>{escape(str(top.get('name', 'none')))}</td>"
        "</tr>"
    )


def _report_css() -> str:
    return "\n".join(
        [
            "body { margin: 0; background: #f8f9ff; color: #111827; "
            "font-family: Public Sans, Arial, sans-serif; }",
            "main { max-width: 1280px; margin: 0 auto; padding: 32px; }",
            "header, .metric, .query, .chart { background: #fff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; }",
            "header { padding: 24px; margin-bottom: 16px; }",
            "h1, h2, p { margin: 0; }",
            "h1 { font-size: 28px; margin-top: 8px; }",
            "h2 { font-size: 18px; margin-bottom: 8px; }",
            ".eyebrow { color: #64748b; font-size: 11px; font-weight: 700; "
            "letter-spacing: .05em; text-transform: uppercase; }",
            ".metrics { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); "
            "gap: 12px; margin-bottom: 16px; }",
            ".metric { padding: 16px; }",
            ".metric span { display: block; color: #64748b; font-size: 11px; "
            "font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }",
            ".metric strong { display: block; font-size: 26px; margin-top: 8px; }",
            ".chart { padding: 18px; margin-bottom: 16px; }",
            ".bar-row { display: grid; grid-template-columns: 260px 1fr 80px; "
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
            ".hit td:nth-child(3) { color: #047857; font-weight: 700; }",
            ".miss td:nth-child(3) { color: #b91c1c; font-weight: 700; }",
            "@media (max-width: 900px) { .metrics { grid-template-columns: 1fr 1fr; } "
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


def _live_query_limit() -> int:
    raw_value = os.getenv("PHARMAIDE_LIVE_RAG_QUERY_LIMIT")
    if raw_value is None:
        return DEFAULT_QUERY_LIMIT
    return max(1, int(raw_value))


def _threshold(env_name: str, default: float) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default
    return float(raw_value)
