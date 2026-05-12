"""Medication grounding node for the Sprint 3 analysis graph."""

import httpx
import structlog

from app.agents.analysis_schemas import AnalysisState, MedicationGrounding, MedicationState
from app.services.rxnorm import RxNormMatch, find_rxcui

log = structlog.get_logger(__name__)


async def ground_medications(
    state: AnalysisState,
    *,
    rxnorm_client: httpx.AsyncClient,
) -> AnalysisState:
    """Ground state medications to RxNorm without failing on upstream misses.

    RxNorm outages degrade the analysis because pharmacist review can still
    proceed with unmatched medications; schema errors remain real failures.
    """
    groundings: list[MedicationGrounding] = []
    degraded = bool(state.get("degraded", False))

    for medication in state.get("medications", []):
        try:
            match = await find_rxcui(rxnorm_client, medication["name"])
        except httpx.HTTPError as exc:
            degraded = True
            _log_rxnorm_failure(medication, exc)
            match = None

        groundings.append(_build_grounding(medication, match))

    result = state.copy()
    result["groundings"] = groundings
    result["degraded"] = degraded
    _log_grounding_summary(result)
    return result


def _build_grounding(
    medication: MedicationState,
    match: RxNormMatch | None,
) -> MedicationGrounding:
    if match is None:
        return MedicationGrounding(
            medication_id=medication["id"],
            medication_name=medication["name"],
            confidence=0,
        )

    return MedicationGrounding(
        medication_id=medication["id"],
        medication_name=medication["name"],
        rxcui=match.rxcui,
        normalized_name=match.name,
        confidence=_confidence_from_rxnorm_score(match.score),
    )


def _confidence_from_rxnorm_score(score: float) -> float:
    """Convert RxNorm approximate scores to the app's 0..1 confidence envelope."""
    return min(max(score / 100, 0), 1)


def _log_rxnorm_failure(medication: MedicationState, exc: httpx.HTTPError) -> None:
    status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    log.warning(
        "rxnorm_grounding_failed",
        medication_id=str(medication["id"]),
        error_type=exc.__class__.__name__,
        status_code=status_code,
    )


def _log_grounding_summary(state: AnalysisState) -> None:
    groundings = state["groundings"]
    log.info(
        "medications_grounded",
        medication_count=len(groundings),
        matched_count=sum(1 for grounding in groundings if grounding.rxcui is not None),
        unmatched_count=sum(1 for grounding in groundings if grounding.rxcui is None),
        degraded=state["degraded"],
        medication_ids=[str(grounding.medication_id) for grounding in groundings],
    )
