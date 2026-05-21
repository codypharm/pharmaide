from tests.evaluations.test_live_rag_products_eval import (
    LiveQueryResult,
    LiveRetrievedCitation,
    _live_metrics_summary,
    _live_report_payload,
)


def test_live_report_payload_groups_metrics_by_relevance_type() -> None:
    results = [
        _query_result(
            expected_name="Target A",
            relevant_names=("Target A", "Alternative A"),
            relevance_type="same_active_ingredient",
            retrieved=[
                _citation(rank=1, name="Target A", exact=True, related=True),
                _citation(rank=2, name="Alternative A", exact=False, related=True),
            ],
        ),
        _query_result(
            expected_name="Target B",
            relevant_names=("Target B",),
            relevance_type="exact_product",
            retrieved=[
                _citation(rank=1, name="Distractor", exact=False, related=False),
                _citation(rank=2, name="Target B", exact=True, related=True),
            ],
        ),
    ]

    payload = _live_report_payload(results, _live_metrics_summary(results, chunk_count=2))

    by_type = payload["metrics_by_relevance_type"]
    assert by_type["same_active_ingredient"]["query_count"] == 1
    assert by_type["same_active_ingredient"]["strict_precision_at_5"] == 0.4
    assert by_type["same_active_ingredient"]["mrr"] == 1.0
    assert by_type["exact_product"]["query_count"] == 1
    assert by_type["exact_product"]["strict_precision_at_5"] == 0.2
    assert by_type["exact_product"]["mrr"] == 0.5


def _query_result(
    *,
    expected_name: str,
    relevant_names: tuple[str, ...],
    relevance_type: str,
    retrieved: list[LiveRetrievedCitation],
) -> LiveQueryResult:
    return LiveQueryResult(
        query=f"query for {expected_name}",
        expected_name=expected_name,
        relevant_names=relevant_names,
        relevance_source="curated" if relevance_type != "exact_product" else "exact_product",
        relevance_type=relevance_type,
        retrieved=tuple(retrieved),
    )


def _citation(
    *,
    rank: int,
    name: str,
    exact: bool,
    related: bool,
) -> LiveRetrievedCitation:
    return LiveRetrievedCitation(
        rank=rank,
        name=name,
        exact_match=exact,
        related_match=related,
        score=1 / rank,
        document_title="products.csv",
        source_uri="products.csv",
    )
