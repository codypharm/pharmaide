"""Drug interaction node for the Sprint 3 analysis graph."""

import structlog

from app.agents.analysis_schemas import AnalysisState, MedicationGrounding

log = structlog.get_logger(__name__)


async def check_interactions(state: AnalysisState) -> AnalysisState:
    """Populate DDI warnings only when a supported provider exists.

    Sprint 3 keeps this node honest: RxNorm can identify drugs, but it is not
    a current DDI source. A future licensed provider can plug in here without
    changing the graph shape.
    """
    grounded = _grounded_medications(state)
    result = state.copy()
    result["ddi_warnings"] = []

    if len(grounded) < 2:
        _log_ddi_skip(
            result,
            grounded_count=len(grounded),
            reason="insufficient_grounded_medications",
        )
        return result

    # TODO(sprint-4): add a licensed DDI provider abstraction here. Preferred
    # examples are Lexicomp, First Databank, Micromedex, Medscape, or DrugBank
    # after license and API access review.
    result["degraded"] = True
    _log_ddi_skip(result, grounded_count=len(grounded), reason="provider_not_configured")
    return result


def _grounded_medications(state: AnalysisState) -> list[MedicationGrounding]:
    return [grounding for grounding in state.get("groundings", []) if grounding.rxcui is not None]


def _log_ddi_skip(state: AnalysisState, *, grounded_count: int, reason: str) -> None:
    log.info(
        "ddi_check_skipped",
        reason=reason,
        grounded_count=grounded_count,
        degraded=state.get("degraded", False),
        medication_ids=[
            str(grounding.medication_id)
            for grounding in state.get("groundings", [])
            if grounding.rxcui is not None
        ],
    )
