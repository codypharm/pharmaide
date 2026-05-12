"""Deterministic medication schedule grammar behavior."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.agents.analysis_schemas import ReminderSlot, Schedule
from app.services.schedule_grammar import FrequencyPattern, compose_schedule, parse_frequency

MEDICATION_ID = UUID("11111111-1111-1111-1111-111111111111")
START = datetime(2026, 5, 12, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("QD", FrequencyPattern(kind="daily_count", doses_per_day=1, human_label="once daily")),
        (
            "Once Daily",
            FrequencyPattern(kind="daily_count", doses_per_day=1, human_label="once daily"),
        ),
        (
            "Once Daily (QD)",
            FrequencyPattern(kind="daily_count", doses_per_day=1, human_label="once daily"),
        ),
        (
            "daily",
            FrequencyPattern(kind="daily_count", doses_per_day=1, human_label="once daily"),
        ),
        ("BID", FrequencyPattern(kind="daily_count", doses_per_day=2, human_label="twice daily")),
        (
            "Twice Daily",
            FrequencyPattern(kind="daily_count", doses_per_day=2, human_label="twice daily"),
        ),
        (
            "Three times daily",
            FrequencyPattern(kind="daily_count", doses_per_day=3, human_label="three times daily"),
        ),
        (
            "TID",
            FrequencyPattern(kind="daily_count", doses_per_day=3, human_label="three times daily"),
        ),
        (
            "QID",
            FrequencyPattern(kind="daily_count", doses_per_day=4, human_label="four times daily"),
        ),
        (
            "Q4H",
            FrequencyPattern(kind="interval_hours", interval_hours=4, human_label="every 4 hours"),
        ),
        (
            "q6h",
            FrequencyPattern(kind="interval_hours", interval_hours=6, human_label="every 6 hours"),
        ),
        (
            "Q8H",
            FrequencyPattern(kind="interval_hours", interval_hours=8, human_label="every 8 hours"),
        ),
        (
            "Q12H",
            FrequencyPattern(
                kind="interval_hours",
                interval_hours=12,
                human_label="every 12 hours",
            ),
        ),
        (
            "Every 6 hours",
            FrequencyPattern(kind="interval_hours", interval_hours=6, human_label="every 6 hours"),
        ),
        ("PRN", FrequencyPattern(kind="prn", human_label="as needed")),
    ],
)
def test_parse_frequency_recognises_supported_patterns(
    text: str,
    expected: FrequencyPattern,
) -> None:
    assert parse_frequency(text) == expected


@pytest.mark.parametrize("text", ["", "with meals", "every morning and night", "weekly"])
def test_parse_frequency_returns_none_for_unsupported_patterns(text: str) -> None:
    assert parse_frequency(text) is None


def test_compose_schedule_builds_daily_count_offsets() -> None:
    pattern = FrequencyPattern(kind="daily_count", doses_per_day=2, human_label="twice daily")

    schedule = compose_schedule(
        medication_id=MEDICATION_ID,
        start_dt=START,
        frequency_pattern=pattern,
        duration_text="2 days",
    )

    assert schedule == Schedule(
        reminders=[
            ReminderSlot(
                medication_id=MEDICATION_ID,
                offset_from_start=timedelta(hours=0),
                human_label="twice daily dose 1",
            ),
            ReminderSlot(
                medication_id=MEDICATION_ID,
                offset_from_start=timedelta(hours=12),
                human_label="twice daily dose 2",
            ),
            ReminderSlot(
                medication_id=MEDICATION_ID,
                offset_from_start=timedelta(hours=24),
                human_label="twice daily dose 1",
            ),
            ReminderSlot(
                medication_id=MEDICATION_ID,
                offset_from_start=timedelta(hours=36),
                human_label="twice daily dose 2",
            ),
        ]
    )


def test_compose_schedule_builds_interval_offsets() -> None:
    pattern = FrequencyPattern(
        kind="interval_hours",
        interval_hours=8,
        human_label="every 8 hours",
    )

    schedule = compose_schedule(
        medication_id=MEDICATION_ID,
        start_dt=START,
        frequency_pattern=pattern,
        duration_text="1 day",
    )

    assert schedule == Schedule(
        reminders=[
            ReminderSlot(
                medication_id=MEDICATION_ID,
                offset_from_start=timedelta(hours=0),
                human_label="every 8 hours dose",
            ),
            ReminderSlot(
                medication_id=MEDICATION_ID,
                offset_from_start=timedelta(hours=8),
                human_label="every 8 hours dose",
            ),
            ReminderSlot(
                medication_id=MEDICATION_ID,
                offset_from_start=timedelta(hours=16),
                human_label="every 8 hours dose",
            ),
        ]
    )


def test_compose_schedule_caps_preview_at_twenty_reminders() -> None:
    pattern = FrequencyPattern(
        kind="interval_hours",
        interval_hours=4,
        human_label="every 4 hours",
    )

    schedule = compose_schedule(
        medication_id=MEDICATION_ID,
        start_dt=START,
        frequency_pattern=pattern,
        duration_text="30 days",
    )

    assert schedule is not None
    assert len(schedule.reminders) == 20
    assert schedule.reminders[-1].offset_from_start == timedelta(hours=76)


@pytest.mark.parametrize("duration_text", ["", "until finished", "two weeks"])
def test_compose_schedule_returns_none_for_unsupported_duration(duration_text: str) -> None:
    pattern = FrequencyPattern(kind="daily_count", doses_per_day=1, human_label="once daily")

    assert (
        compose_schedule(
            medication_id=MEDICATION_ID,
            start_dt=START,
            frequency_pattern=pattern,
            duration_text=duration_text,
        )
        is None
    )


def test_compose_schedule_returns_none_for_prn() -> None:
    pattern = FrequencyPattern(kind="prn", human_label="as needed")

    assert (
        compose_schedule(
            medication_id=MEDICATION_ID,
            start_dt=START,
            frequency_pattern=pattern,
            duration_text="3 days",
        )
        is None
    )
