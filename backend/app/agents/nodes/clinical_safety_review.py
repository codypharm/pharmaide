"""Model-backed clinical safety review node.

This node is an interim fallback while licensed clinical decision-support
access is unavailable. It must never be treated as a database-confirmed DDI
provider result; every output is validated and marked as ``model_review`` for
pharmacist review.
"""

import structlog
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.analysis_schemas import (
    AnalysisState,
    ClinicalSafetyReview,
)

log = structlog.get_logger(__name__)

SAFETY_REVIEW_INSTRUCTIONS = """
You are PharmaAide's interim clinical safety review agent.
Use only the validated AnalysisState content provided in the user prompt.
Do not invent medications, diagnoses, patient facts, lab values, or sourced interaction claims.
possible_interactions must only describe interactions between current treatment medications,
or substances/co-medications explicitly reported in patient_check_ins. Do not list general
label examples such as alcohol, warfarin, lithium, disulfiram, or contraceptives unless they
are present in the validated state.
Do not present findings as database-confirmed drug interaction results.
Return pharmacist-review support only, with source_type fixed to model_review and
requires_pharmacist_review fixed to true.
Prefer cautious missing-information notes over unsupported conclusions.
"""


def build_clinical_safety_agent(
    model: Model | str = "openai:gpt-5",
) -> Agent[None, ClinicalSafetyReview]:
    """Build the typed agent used for interim clinical safety review."""
    return Agent(
        model,
        output_type=ClinicalSafetyReview,
        instructions=SAFETY_REVIEW_INSTRUCTIONS,
        defer_model_check=True,
    )


async def review_clinical_safety(
    state: AnalysisState,
    *,
    agent: Agent[None, ClinicalSafetyReview] | None,
) -> AnalysisState:
    """Attach a validated model review without changing DDI provider results."""
    if agent is None:
        result = state.copy()
        result["clinical_safety_review"] = None
        log.info("clinical_safety_review_skipped", reason="agent_not_configured")
        return result

    try:
        response = await agent.run(_safety_review_prompt(state))
    except Exception as exc:
        result = state.copy()
        result["clinical_safety_review"] = None
        result["degraded"] = True
        log.warning(
            "clinical_safety_review_failed",
            error_type=exc.__class__.__name__,
            degraded=True,
        )
        return result

    review = response.output
    review, filtered_interaction_count = _filter_possible_interactions(state, review)

    result = state.copy()
    result["clinical_safety_review"] = review
    log.info(
        "clinical_safety_review_generated",
        source_type=review.source_type,
        possible_interaction_count=len(review.possible_interactions),
        filtered_interaction_count=filtered_interaction_count,
        monitoring_concern_count=len(review.monitoring_concerns),
        counseling_point_count=len(review.counseling_points),
        missing_information_count=len(review.missing_information),
        confidence=review.confidence,
        requires_pharmacist_review=review.requires_pharmacist_review,
    )
    return result


def _filter_possible_interactions(
    state: AnalysisState,
    review: ClinicalSafetyReview,
) -> tuple[ClinicalSafetyReview, int]:
    """Drop model-suggested interactions that introduce off-regimen entities."""
    allowed_context = _allowed_interaction_context(state)
    filtered = [
        interaction
        for interaction in review.possible_interactions
        if _interaction_targets_are_allowed(interaction, allowed_context)
    ]
    removed_count = len(review.possible_interactions) - len(filtered)
    if removed_count == 0:
        return review, 0
    return review.model_copy(update={"possible_interactions": filtered}), removed_count


def _allowed_interaction_context(state: AnalysisState) -> str:
    medication_terms = [
        medication["name"]
        for medication in state.get("medications", [])
        if medication.get("name")
    ]
    reported_terms = [
        check_in.message
        for check_in in state.get("patient_check_ins", [])
    ]
    return " ".join([*medication_terms, *reported_terms]).lower()


def _interaction_targets_are_allowed(interaction: str, allowed_context: str) -> bool:
    header = interaction.split(":", maxsplit=1)[0]
    targets = [target.strip() for target in header.split("+")]
    if len(targets) < 2:
        return False
    return all(_target_is_allowed(target, allowed_context) for target in targets)


def _target_is_allowed(target: str, allowed_context: str) -> bool:
    normalised = target.lower().replace("(", " ").replace(")", " ")
    candidates = [
        part.strip(" ,.;")
        for part in normalised.replace("/", " ").split()
        if len(part.strip(" ,.;")) >= 4
    ]
    return any(candidate in allowed_context for candidate in candidates)


def _safety_review_prompt(state: AnalysisState) -> str:
    return "\n".join(
        [
            "Review this validated AnalysisState for pharmacist safety review.",
            "This is an AI model review, not a licensed DDI database result.",
            "validated AnalysisState:",
            f"degraded: {state.get('degraded', False)}",
            f"medications:\n{_medications_section(state)}",
            f"patient_check_ins:\n{_patient_check_ins_section(state)}",
            f"groundings:\n{_groundings_section(state)}",
            f"ddi_warnings:\n{_ddi_section(state)}",
            f"kb_citations:\n{_kb_citations_section(state)}",
        ]
    )


def _medications_section(state: AnalysisState) -> str:
    medications = state.get("medications", [])
    if not medications:
        return "- none"
    return "\n".join(
        (
            f"- id={medication['id']} name={medication['name']} dosage={medication['dosage']} "
            f"frequency={medication['frequency']} duration={medication['duration']} "
            f"objective={medication.get('objective') or 'unavailable'}"
        )
        for medication in medications
    )


def _patient_check_ins_section(state: AnalysisState) -> str:
    check_ins = state.get("patient_check_ins", [])
    if not check_ins:
        return "- none"
    return "\n".join(
        (
            f"- id={check_in.id} report_type={check_in.report_type} source={check_in.source} "
            f"observed_at={check_in.observed_at or 'unavailable'} "
            f"created_at={check_in.created_at}\n  message={check_in.message}"
        )
        for check_in in check_ins
    )


def _groundings_section(state: AnalysisState) -> str:
    groundings = state.get("groundings", [])
    if not groundings:
        return "- none"
    return "\n".join(
        (
            f"- medication_id={grounding.medication_id} rxcui={grounding.rxcui or 'unmatched'} "
            f"normalized_name={grounding.normalized_name or 'unavailable'} "
            f"confidence={grounding.confidence}"
        )
        for grounding in groundings
    )


def _ddi_section(state: AnalysisState) -> str:
    warnings = state.get("ddi_warnings", [])
    if not warnings:
        return "- none or provider unavailable"
    return "\n".join(
        (
            f"- medication_ids={','.join(str(id_) for id_ in warning.medication_ids)} "
            f"severity={warning.severity} source={warning.source} description={warning.description}"
        )
        for warning in warnings
    )


def _kb_citations_section(state: AnalysisState) -> str:
    citations = state.get("kb_citations", [])
    if not citations:
        return "- none"
    return "\n".join(
        (
            f"- chunk_id={citation.chunk_id} document_title={citation.document_title} "
            f"source_type={citation.source_type} score={citation.score} "
            f"source_uri={citation.source_uri}\n  text={citation.text}"
        )
        for citation in citations
    )
