"""Schedule generation node for the Sprint 3 analysis graph."""

from datetime import datetime

import structlog

from app.agents.analysis_schemas import AnalysisState, MedicationState, ReminderSlot, Schedule
from app.services.schedule_grammar import compose_schedule, parse_frequency

log = structlog.get_logger(__name__)


async def generate_schedule(
    state: AnalysisState,
    *,
    start_dt: datetime,
) -> AnalysisState:
    """Generate deterministic reminder previews before the LLM fallback step."""
    reminders: list[ReminderSlot] = []
    unsupported_medication_ids: list[str] = []

    for medication in state.get("medications", []):
        medication_schedule = _schedule_medication(medication, start_dt=start_dt)
        if medication_schedule is None:
            unsupported_medication_ids.append(str(medication["id"]))
            continue
        reminders.extend(medication_schedule.reminders)

    result = state.copy()
    result["schedule"] = _combined_schedule(reminders)
    result["needs_llm_parse"] = bool(state.get("needs_llm_parse", False)) or bool(
        unsupported_medication_ids
    )
    _log_schedule_summary(result, unsupported_medication_ids=unsupported_medication_ids)
    return result


def _schedule_medication(
    medication: MedicationState,
    *,
    start_dt: datetime,
) -> Schedule | None:
    frequency_pattern = parse_frequency(medication["frequency"])
    if frequency_pattern is None:
        return None
    return compose_schedule(
        medication_id=medication["id"],
        start_dt=start_dt,
        frequency_pattern=frequency_pattern,
        duration_text=medication["duration"],
    )


def _combined_schedule(reminders: list[ReminderSlot]) -> Schedule | None:
    if not reminders:
        return None
    return Schedule(
        reminders=sorted(
            reminders,
            key=lambda reminder: (reminder.offset_from_start, str(reminder.medication_id)),
        )
    )


def _log_schedule_summary(
    state: AnalysisState,
    *,
    unsupported_medication_ids: list[str],
) -> None:
    medication_ids = [str(medication["id"]) for medication in state.get("medications", [])]
    schedule = state.get("schedule")
    scheduled_medication_ids = (
        {str(reminder.medication_id) for reminder in schedule.reminders}
        if schedule is not None
        else set()
    )
    log.info(
        "schedule_generated",
        medication_count=len(medication_ids),
        scheduled_count=len(scheduled_medication_ids),
        reminder_count=len(schedule.reminders) if schedule is not None else 0,
        needs_llm_parse=state["needs_llm_parse"],
        medication_ids=medication_ids,
        unsupported_medication_ids=unsupported_medication_ids,
    )
