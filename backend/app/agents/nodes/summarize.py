"""Clinical reasoning summary node for the Sprint 3 analysis graph."""

import structlog
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.analysis_schemas import (
    AnalysisState,
    ClinicalReasoning,
    ClinicalReasoningWithSchedule,
    ClinicalSafetyReview,
    ReminderSlot,
    Schedule,
)
from app.agents.model_calls import run_model_with_retry

log = structlog.get_logger(__name__)

SAFETY_REVIEW_INTERACTION_FLAG = "Clinical safety review found possible interaction concerns."
SAFETY_REVIEW_MONITORING_FLAG = "Clinical safety review found monitoring concerns."
SAFETY_REVIEW_MISSING_INFO_FLAG = (
    "Clinical safety review found missing information for pharmacist review."
)

SUMMARY_INSTRUCTIONS = """
You are PharmaAide's pharmacist-review summary agent.
Use only the validated AnalysisState content provided in the user prompt.
Never invent medications, diagnoses, interactions, schedules, patient facts, or monitoring outcomes.
If data is missing, explicitly say it is unavailable and keep confidence lower.
Return concise clinical reasoning for pharmacist review, not patient-facing advice.
"""

SCHEDULE_INSTRUCTIONS = (
    SUMMARY_INSTRUCTIONS
    + "\nWhen needs_llm_parse is true, propose Schedule.reminders only for medications whose "
    "frequency or duration could not be parsed deterministically. Use only the medication "
    "instructions present in the validated state. Do not invent frequency, duration, dose timing, "
    "patient condition, or clinical rationale. Do not create reminders for PRN/as-needed "
    "medications unless the provided instruction contains explicit timing. Existing deterministic "
    "reminders are already in state; do not duplicate them. Return null schedule when timing "
    "cannot be inferred with high confidence. Any proposed reminders are pharmacist-review "
    "drafts, not patient-facing instructions."
)


def build_summary_agent(
    model: Model | str = "openai:gpt-5-mini",
) -> Agent[None, ClinicalReasoning]:
    """Build the typed PydanticAI agent used for clinical summary output."""
    return Agent(
        model,
        output_type=ClinicalReasoning,
        instructions=SUMMARY_INSTRUCTIONS,
        defer_model_check=True,
    )


def build_summary_with_schedule_agent(
    model: Model | str = "openai:gpt-5-mini",
) -> Agent[None, ClinicalReasoningWithSchedule]:
    """Build the typed agent used when ambiguous schedules need LLM parsing."""
    return Agent(
        model,
        output_type=ClinicalReasoningWithSchedule,
        instructions=SCHEDULE_INSTRUCTIONS,
        defer_model_check=True,
    )


async def summarize_treatment(
    state: AnalysisState,
    *,
    agent: Agent[None, ClinicalReasoning] | None = None,
    schedule_agent: Agent[None, ClinicalReasoningWithSchedule] | None = None,
) -> AnalysisState:
    """Ask the LLM for typed ClinicalReasoning and store only validated output."""
    if state.get("needs_llm_parse", False):
        return await _summarize_with_schedule(state, agent=schedule_agent)

    summary_agent = agent or build_summary_agent()
    try:
        result = await run_model_with_retry(
            summary_agent,
            _summary_prompt(state),
            operation="summarize_treatment",
        )
    except Exception as exc:
        return _fallback_summary_state(state, exc, needs_llm_parse=False)

    reasoning = _apply_clinical_safety_guard(state, result.output)

    next_state = state.copy()
    next_state["reasoning"] = reasoning
    _log_reasoning_summary(next_state, reasoning)
    return next_state


async def _summarize_with_schedule(
    state: AnalysisState,
    *,
    agent: Agent[None, ClinicalReasoningWithSchedule] | None,
) -> AnalysisState:
    summary_agent = agent or build_summary_with_schedule_agent()
    try:
        result = await run_model_with_retry(
            summary_agent,
            _summary_prompt(state),
            operation="summarize_treatment_with_schedule",
        )
    except Exception as exc:
        return _fallback_summary_state(state, exc, needs_llm_parse=True)

    output = result.output

    next_state = state.copy()
    reasoning = _apply_clinical_safety_guard(state, output.reasoning)
    next_state["reasoning"] = reasoning
    if output.schedule is not None:
        next_state["schedule"] = _merge_schedules(state.get("schedule"), output.schedule)
    _log_reasoning_summary(next_state, reasoning)
    return next_state


def _merge_schedules(existing: Schedule | None, proposed: Schedule) -> Schedule:
    reminders = [*(existing.reminders if existing is not None else []), *proposed.reminders]
    return Schedule(reminders=_sort_reminders(reminders))


def _sort_reminders(reminders: list[ReminderSlot]) -> list[ReminderSlot]:
    return sorted(
        reminders,
        key=lambda reminder: (reminder.offset_from_start, str(reminder.medication_id)),
    )


def _fallback_summary_state(
    state: AnalysisState,
    exc: Exception,
    *,
    needs_llm_parse: bool,
) -> AnalysisState:
    """Preserve usable deterministic analysis when the summary model is unavailable."""
    reasoning = ClinicalReasoning(
        summary="Model-generated clinical summary is unavailable. Pharmacist review is required.",
        red_flags=_fallback_red_flags(state, needs_llm_parse=needs_llm_parse),
        confidence=0,
    )
    result = state.copy()
    result["degraded"] = True
    result["reasoning"] = reasoning
    log.warning(
        "summary_generation_failed",
        error_type=exc.__class__.__name__,
        needs_llm_parse=needs_llm_parse,
        degraded=True,
    )
    _log_reasoning_summary(result, reasoning)
    return result


def _fallback_red_flags(state: AnalysisState, *, needs_llm_parse: bool) -> list[str]:
    flags = ["Model-generated clinical summary unavailable; pharmacist review required."]
    if state.get("degraded", False):
        flags.append("Analysis is degraded; verify upstream results before acting.")
    if state.get("ddi_warnings"):
        flags.append("Interaction warnings require pharmacist review.")
    if needs_llm_parse:
        flags.append("Some schedule instructions need pharmacist review.")
    return flags


def _apply_clinical_safety_guard(
    state: AnalysisState,
    reasoning: ClinicalReasoning,
) -> ClinicalReasoning:
    """Ensure pharmacist-facing summaries cannot drop safety-review concerns."""
    review = state.get("clinical_safety_review")
    if review is None:
        return reasoning

    safety_flags = _safety_review_red_flags(review)
    if not safety_flags:
        return reasoning

    # The summary model sees the safety review in its prompt, but this guard is
    # the durable boundary that keeps clinically important concerns visible.
    return ClinicalReasoning(
        summary=reasoning.summary,
        red_flags=_append_unique(reasoning.red_flags, safety_flags),
        confidence=min(reasoning.confidence, review.confidence),
    )


def _safety_review_red_flags(review: ClinicalSafetyReview) -> list[str]:
    flags: list[str] = []
    if review.possible_interactions:
        flags.append(SAFETY_REVIEW_INTERACTION_FLAG)
    if review.monitoring_concerns:
        flags.append(SAFETY_REVIEW_MONITORING_FLAG)
    if review.missing_information:
        flags.append(SAFETY_REVIEW_MISSING_INFO_FLAG)
    return flags


def _append_unique(existing: list[str], additions: list[str]) -> list[str]:
    result = list(existing)
    for addition in additions:
        if addition not in result:
            result.append(addition)
    return result


def _summary_prompt(state: AnalysisState) -> str:
    return "\n".join(
        [
            "Summarize this validated AnalysisState for pharmacist review.",
            "validated AnalysisState:",
            f"degraded: {state.get('degraded', False)}",
            f"needs_llm_parse: {state.get('needs_llm_parse', False)}",
            f"medications:\n{_medications_section(state)}",
            f"patient_check_ins:\n{_patient_check_ins_section(state)}",
            f"groundings:\n{_groundings_section(state)}",
            f"ddi_warnings:\n{_ddi_section(state)}",
            f"schedule:\n{_schedule_section(state)}",
            f"kb_citations:\n{_kb_citations_section(state)}",
            f"clinical_safety_review:\n{_clinical_safety_review_section(state)}",
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


def _schedule_section(state: AnalysisState) -> str:
    schedule = state.get("schedule")
    if schedule is None:
        return "- unavailable"
    return "\n".join(
        (
            f"- medication_id={slot.medication_id} offset={slot.offset_from_start} "
            f"label={slot.human_label}"
        )
        for slot in schedule.reminders[:20]
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


def _clinical_safety_review_section(state: AnalysisState) -> str:
    review = state.get("clinical_safety_review")
    if review is None:
        return "- none"
    return "\n".join(
        [
            f"- source_type={review.source_type}",
            f"- requires_pharmacist_review={review.requires_pharmacist_review}",
            f"- confidence={review.confidence}",
            f"- possible_interactions={review.possible_interactions}",
            f"- monitoring_concerns={review.monitoring_concerns}",
            f"- counseling_points={review.counseling_points}",
            f"- missing_information={review.missing_information}",
        ]
    )


def _log_reasoning_summary(state: AnalysisState, reasoning: ClinicalReasoning) -> None:
    schedule = state.get("schedule")
    safety_review = state.get("clinical_safety_review")
    # Resolve after test/runtime logging configuration so cached structlog
    # proxies do not pin an older renderer.
    current_log = structlog.get_logger(__name__)
    current_log.info(
        "clinical_reasoning_generated",
        medication_count=len(state.get("medications", [])),
        patient_check_in_count=len(state.get("patient_check_ins", [])),
        grounding_count=len(state.get("groundings", [])),
        ddi_warning_count=len(state.get("ddi_warnings", [])),
        reminder_count=len(schedule.reminders) if schedule is not None else 0,
        red_flag_count=len(reasoning.red_flags),
        confidence=reasoning.confidence,
        safety_review_concern_count=_safety_review_concern_count(safety_review),
        degraded=state.get("degraded", False),
        needs_llm_parse=state.get("needs_llm_parse", False),
    )


def _safety_review_concern_count(review: ClinicalSafetyReview | None) -> int:
    if review is None:
        return 0
    return (
        len(review.possible_interactions)
        + len(review.monitoring_concerns)
        + len(review.missing_information)
    )
