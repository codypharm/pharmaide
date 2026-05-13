"""Clinical reasoning summary node for the Sprint 3 analysis graph."""

import structlog
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.analysis_schemas import (
    AnalysisState,
    ClinicalReasoning,
    ClinicalReasoningWithSchedule,
    ReminderSlot,
    Schedule,
)

log = structlog.get_logger(__name__)

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
    result = await summary_agent.run(_summary_prompt(state))
    reasoning = result.output

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
    result = await summary_agent.run(_summary_prompt(state))
    output = result.output

    next_state = state.copy()
    next_state["reasoning"] = output.reasoning
    if output.schedule is not None:
        next_state["schedule"] = _merge_schedules(state.get("schedule"), output.schedule)
    _log_reasoning_summary(next_state, output.reasoning)
    return next_state


def _merge_schedules(existing: Schedule | None, proposed: Schedule) -> Schedule:
    reminders = [*(existing.reminders if existing is not None else []), *proposed.reminders]
    return Schedule(reminders=_sort_reminders(reminders))


def _sort_reminders(reminders: list[ReminderSlot]) -> list[ReminderSlot]:
    return sorted(
        reminders,
        key=lambda reminder: (reminder.offset_from_start, str(reminder.medication_id)),
    )


def _summary_prompt(state: AnalysisState) -> str:
    return "\n".join(
        [
            "Summarize this validated AnalysisState for pharmacist review.",
            "validated AnalysisState:",
            f"degraded: {state.get('degraded', False)}",
            f"needs_llm_parse: {state.get('needs_llm_parse', False)}",
            f"medications:\n{_medications_section(state)}",
            f"groundings:\n{_groundings_section(state)}",
            f"ddi_warnings:\n{_ddi_section(state)}",
            f"schedule:\n{_schedule_section(state)}",
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


def _log_reasoning_summary(state: AnalysisState, reasoning: ClinicalReasoning) -> None:
    schedule = state.get("schedule")
    log.info(
        "clinical_reasoning_generated",
        medication_count=len(state.get("medications", [])),
        grounding_count=len(state.get("groundings", [])),
        ddi_warning_count=len(state.get("ddi_warnings", [])),
        reminder_count=len(schedule.reminders) if schedule is not None else 0,
        red_flag_count=len(reasoning.red_flags),
        confidence=reasoning.confidence,
        degraded=state.get("degraded", False),
        needs_llm_parse=state.get("needs_llm_parse", False),
    )
