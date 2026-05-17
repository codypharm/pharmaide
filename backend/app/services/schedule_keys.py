"""Stable keys for schedule-derived workflow markers."""

from datetime import timedelta

from app.agents.analysis_schemas import ReminderSlot


def reminder_key_for_slot(reminder: ReminderSlot) -> str:
    """Return the deterministic audit key for one schedule reminder."""
    return (
        f"{reminder.medication_id}:"
        f"{_serialise_offset(reminder.offset_from_start)}:"
        f"{reminder.human_label}"
    )


def _serialise_offset(offset: timedelta) -> str:
    seconds = int(offset.total_seconds())
    if seconds == 0:
        return "PT0S"
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    date_part = f"{days}D" if days else ""
    time_part = "".join(
        [
            f"{hours}H" if hours else "",
            f"{minutes}M" if minutes else "",
            f"{seconds}S" if seconds else "",
        ]
    )
    if time_part:
        return f"{sign}P{date_part}T{time_part}"
    return f"{sign}P{date_part}"
