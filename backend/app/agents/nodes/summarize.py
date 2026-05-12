"""Clinical reasoning summary node for the Sprint 3 analysis graph."""

import structlog
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.analysis_schemas import AnalysisState, ClinicalReasoning

log = structlog.get_logger(__name__)

SUMMARY_INSTRUCTIONS = """
You are PharmaAide's pharmacist-review summary agent.
Use only the validated AnalysisState content provided in the user prompt.
Never invent medications, diagnoses, interactions, schedules, patient facts, or monitoring outcomes.
If data is missing, explicitly say it is unavailable and keep confidence lower.
Return concise clinical reasoning for pharmacist review, not patient-facing advice.
"""


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


async def summarize_treatment(
    state: AnalysisState,
    *,
    agent: Agent[None, ClinicalReasoning] | None = None,
) -> AnalysisState:
    """Ask the LLM for typed ClinicalReasoning and store only validated output."""
    summary_agent = agent or build_summary_agent()
    result = await summary_agent.run(_summary_prompt(state))
    reasoning = result.output

    next_state = state.copy()
    next_state["reasoning"] = reasoning
    _log_reasoning_summary(next_state, reasoning)
    return next_state


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
