"""Pydantic envelopes for treatment analysis outputs."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.analysis_schemas import (
    AnalysisResult,
    ClinicalReasoning,
    DDIWarning,
    MedicationGrounding,
    ReminderSlot,
    Schedule,
)


def test_analysis_result_composes_groundings_ddis_schedule_and_reasoning() -> None:
    medication_id = uuid4()
    result = AnalysisResult(
        groundings=[
            MedicationGrounding(
                medication_id=medication_id,
                medication_name="Lisinopril",
                rxcui="29046",
                normalized_name="lisinopril",
                confidence=0.93,
            )
        ],
        ddi_warnings=[
            DDIWarning(
                medication_ids=[medication_id, uuid4()],
                severity="major",
                description="Monitor closely.",
                source="rxnorm",
            )
        ],
        schedule=Schedule(
            reminders=[
                ReminderSlot(
                    medication_id=medication_id,
                    offset_from_start=timedelta(hours=8),
                    human_label="Day 1, 08:00",
                )
            ]
        ),
        reasoning=ClinicalReasoning(
            summary="Grounded one medication.",
            red_flags=[],
            confidence=0.88,
        ),
        degraded=False,
    )

    payload = result.model_dump(mode="json")

    assert payload["groundings"][0]["rxcui"] == "29046"
    assert payload["ddi_warnings"][0]["severity"] == "major"
    assert payload["schedule"]["reminders"][0]["human_label"] == "Day 1, 08:00"
    assert payload["reasoning"]["summary"] == "Grounded one medication."
    assert payload["degraded"] is False
    assert payload["partial_results"] is False
    assert payload["completed_stages"] == []


def test_ddi_warning_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        DDIWarning(
            medication_ids=[uuid4(), uuid4()],
            severity="critical",
            description="Unsupported severity.",
            source="rxnorm",
        )


def test_clinical_reasoning_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        ClinicalReasoning(
            summary="Too certain.",
            red_flags=[],
            confidence=1.5,
        )


def test_llm_envelopes_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ClinicalReasoning.model_validate(
            {
                "summary": "Do not accept invented shape.",
                "red_flags": [],
                "confidence": 0.5,
                "unvalidated_extra": "nope",
            }
        )
