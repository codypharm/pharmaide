"""Deterministic medication schedule grammar behavior."""

import pytest

from app.services.schedule_grammar import FrequencyPattern, parse_frequency


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
