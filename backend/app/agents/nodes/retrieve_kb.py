"""Knowledge-base retrieval node for the treatment analysis graph."""

from collections.abc import Awaitable, Callable
from uuid import UUID

import structlog

from app.agents.analysis_schemas import AnalysisState, KBCitation

KnowledgeRetriever = Callable[[str, UUID | None], Awaitable[list[KBCitation]]]

log = structlog.get_logger(__name__)


async def retrieve_kb_citations(
    state: AnalysisState,
    *,
    retriever: KnowledgeRetriever | None,
) -> AnalysisState:
    """Attach retrieved KB citations without making clinical conclusions."""
    if retriever is None:
        result = state.copy()
        result["kb_citations"] = []
        log.info("kb_retrieval_skipped", reason="retriever_not_configured")
        return result

    query = _query_from_state(state)
    try:
        citations = await retriever(query, state.get("treatment_id"))
    except Exception:
        result = state.copy()
        result["kb_citations"] = []
        result["degraded"] = True
        log.warning(
            "kb_retrieval_failed",
            treatment_id=str(state["treatment_id"]) if "treatment_id" in state else None,
        )
        return result

    result = state.copy()
    result["kb_citations"] = citations
    log.info(
        "kb_citations_retrieved",
        citation_count=len(citations),
        top_score=citations[0].score if citations else None,
        treatment_id=str(state["treatment_id"]) if "treatment_id" in state else None,
    )
    return result


def _query_from_state(state: AnalysisState) -> str:
    medications = state.get("medications", [])
    if not medications:
        return "No medications available."
    return "\n".join(
        (
            f"- {medication['name']} {medication['dosage']} "
            f"{medication['frequency']} for {medication['duration']}; "
            f"objective={medication.get('objective') or 'unavailable'}"
        )
        for medication in medications
    )
