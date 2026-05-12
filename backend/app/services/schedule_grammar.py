"""Deterministic schedule grammar for common medication frequencies."""

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FrequencyKind = Literal["daily_count", "interval_hours", "prn"]

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
