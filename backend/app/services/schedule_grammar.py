"""Deterministic schedule grammar for common medication frequencies."""

import re
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.agents.analysis_schemas import ReminderSlot, Schedule

FrequencyKind = Literal["daily_count", "interval_hours", "prn"]
MAX_REMINDER_PREVIEW = 20

_DAILY_COUNTS: dict[str, tuple[int, str]] = {
    "qd": (1, "once daily"),
    "daily": (1, "once daily"),
    "once daily": (1, "once daily"),
    "bid": (2, "twice daily"),
    "twice daily": (2, "twice daily"),
    "tid": (3, "three times daily"),
    "three times daily": (3, "three times daily"),
    "qid": (4, "four times daily"),
}
_INTERVAL_RE = re.compile(r"^(?:q|every\s+)(?P<hours>\d{1,2})h?(?:\s+hours?)?$")
_DURATION_RE = re.compile(r"^(?P<count>\d+)\s+(?P<unit>day|days|week|weeks)$")


class FrequencyPattern(BaseModel):
    """Parsed frequency shape used by deterministic schedule generation."""

    kind: FrequencyKind
    doses_per_day: int | None = Field(default=None, ge=1, le=24)
    interval_hours: int | None = Field(default=None, ge=1, le=24)
    human_label: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_shape(self) -> "FrequencyPattern":
        if self.kind == "daily_count" and self.doses_per_day is None:
            raise ValueError("daily_count requires doses_per_day")
        if self.kind == "interval_hours" and self.interval_hours is None:
            raise ValueError("interval_hours requires interval_hours")
        return self


def parse_frequency(text: str) -> FrequencyPattern | None:
    """Parse a pharmacist-entered frequency into a deterministic pattern."""
    normalised = _normalise_frequency(text)
    if not normalised:
        return None

    daily = _DAILY_COUNTS.get(normalised)
    if daily is not None:
        doses_per_day, human_label = daily
        return FrequencyPattern(
            kind="daily_count",
            doses_per_day=doses_per_day,
            human_label=human_label,
        )

    interval_hours = _parse_interval_hours(normalised)
    if interval_hours is not None:
        return FrequencyPattern(
            kind="interval_hours",
            interval_hours=interval_hours,
            human_label=f"every {interval_hours} hours",
        )

    if normalised == "prn":
        return FrequencyPattern(kind="prn", human_label="as needed")

    return None


def compose_schedule(
    *,
    medication_id: UUID,
    start_dt: datetime,
    frequency_pattern: FrequencyPattern,
    duration_text: str,
) -> Schedule | None:
    """Build a deterministic reminder preview from parsed frequency and duration.

    ``start_dt`` is intentionally injected by callers so this module never reads
    wall-clock time during tests or background graph execution.
    """
    del start_dt
    duration_days = _parse_duration_days(duration_text)
    if duration_days is None or frequency_pattern.kind == "prn":
        return None

    if frequency_pattern.kind == "daily_count":
        offsets = _daily_count_offsets(frequency_pattern, duration_days)
    else:
        offsets = _interval_offsets(frequency_pattern, duration_days)

    return Schedule(
        reminders=[
            ReminderSlot(
                medication_id=medication_id,
                offset_from_start=offset,
                human_label=label,
            )
            for offset, label in offsets[:MAX_REMINDER_PREVIEW]
        ]
    )


def _normalise_frequency(text: str) -> str:
    value = text.strip().lower()
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_interval_hours(text: str) -> int | None:
    match = _INTERVAL_RE.match(text)
    if match is None:
        return None
    hours = int(match.group("hours"))
    if hours not in {4, 6, 8, 12}:
        return None
    return hours


def _parse_duration_days(text: str) -> int | None:
    match = _DURATION_RE.match(text.strip().lower())
    if match is None:
        return None

    count = int(match.group("count"))
    unit = match.group("unit")
    if count <= 0:
        return None
    if unit in {"week", "weeks"}:
        return count * 7
    return count


def _daily_count_offsets(
    frequency_pattern: FrequencyPattern,
    duration_days: int,
) -> list[tuple[timedelta, str]]:
    assert frequency_pattern.doses_per_day is not None
    spacing_hours = 24 // frequency_pattern.doses_per_day
    return [
        (
            timedelta(days=day, hours=dose_index * spacing_hours),
            f"{frequency_pattern.human_label} dose {dose_index + 1}",
        )
        for day in range(duration_days)
        for dose_index in range(frequency_pattern.doses_per_day)
    ]


def _interval_offsets(
    frequency_pattern: FrequencyPattern,
    duration_days: int,
) -> list[tuple[timedelta, str]]:
    assert frequency_pattern.interval_hours is not None
    duration_hours = duration_days * 24
    return [
        (timedelta(hours=hour), f"{frequency_pattern.human_label} dose")
        for hour in range(0, duration_hours, frequency_pattern.interval_hours)
    ]
