"""DDI fallback boundary evaluation cases.

Until a licensed interaction provider is configured, the analysis graph must
keep provider-confirmed DDI warnings empty. Model-backed clinical safety review
may raise pharmacist-review concerns, but it must stay labelled as an interim
model review instead of masquerading as a database interaction result.
"""

from uuid import UUID

import pytest
from pydantic_ai.models.test import TestModel

from app.agents.analysis_schemas import AnalysisState, MedicationGrounding
from app.agents.nodes.clinical_safety_review import (
    build_clinical_safety_agent,
    review_clinical_safety,
)
from app.agents.nodes.interactions import check_interactions
from app.agents.nodes.summarize import (
    SAFETY_REVIEW_INTERACTION_FLAG,
    build_summary_agent,
    summarize_treatment,
)

pytestmark = pytest.mark.clinical_eval

AMOXICILLIN_ID = UUID("11111111-1111-4111-8111-111111111111")
METRONIDAZOLE_ID = UUID("22222222-2222-4222-8222-222222222222")


async def test_ddi_fallback_eval_keeps_model_review_separate_from_provider_ddi() -> None:
    checked = await check_interactions(_grounded_antibiotic_state())

    assert checked["ddi_warnings"] == []
    assert checked["degraded"] is True

    reviewed = await review_clinical_safety(
        checked,
        agent=build_clinical_safety_agent(
            model=TestModel(
                custom_output_args={
                    "source_type": "model_review",
                    "possible_interactions": [
                        "Amoxicillin + Metronidazole: overlapping gastrointestinal effects."
                    ],
                    "monitoring_concerns": [],
                    "counseling_points": [],
                    "missing_information": [],
                    "confidence": 0.67,
                    "requires_pharmacist_review": True,
                }
            )
        ),
    )

    assert reviewed["ddi_warnings"] == []
    assert reviewed["clinical_safety_review"] is not None
    assert reviewed["clinical_safety_review"].source_type == "model_review"
    assert reviewed["clinical_safety_review"].requires_pharmacist_review is True
    assert reviewed["clinical_safety_review"].possible_interactions == [
        "Amoxicillin + Metronidazole: overlapping gastrointestinal effects."
    ]


async def test_ddi_fallback_eval_summary_surfaces_model_review_as_pharmacist_flag() -> None:
    reviewed = await review_clinical_safety(
        await check_interactions(_grounded_antibiotic_state()),
        agent=build_clinical_safety_agent(
            model=TestModel(
                custom_output_args={
                    "source_type": "model_review",
                    "possible_interactions": [
                        "Amoxicillin + Metronidazole: overlapping gastrointestinal effects."
                    ],
                    "monitoring_concerns": [],
                    "counseling_points": [],
                    "missing_information": [],
                    "confidence": 0.67,
                    "requires_pharmacist_review": True,
                }
            )
        ),
    )

    summarized = await summarize_treatment(
        reviewed,
        agent=build_summary_agent(
            model=TestModel(
                custom_output_args={
                    "summary": "Review the antibiotic course before patient counselling.",
                    "red_flags": [],
                    "confidence": 0.93,
                }
            )
        ),
    )

    assert summarized["ddi_warnings"] == []
    assert summarized["reasoning"] is not None
    assert SAFETY_REVIEW_INTERACTION_FLAG in summarized["reasoning"].red_flags
    assert summarized["reasoning"].confidence == 0.67
    assert "database-confirmed" not in summarized["reasoning"].summary.lower()
    assert "licensed ddi" not in summarized["reasoning"].summary.lower()


def _grounded_antibiotic_state() -> AnalysisState:
    return {
        "medications": [
            {
                "id": AMOXICILLIN_ID,
                "name": "Amoxicillin",
                "dosage": "1 g",
                "frequency": "Twice Daily (BID)",
                "duration": "14 days",
                "objective": None,
            },
            {
                "id": METRONIDAZOLE_ID,
                "name": "Metronidazole",
                "dosage": "400 mg",
                "frequency": "Three Times Daily (TID)",
                "duration": "7 days",
                "objective": None,
            },
        ],
        "groundings": [
            MedicationGrounding(
                medication_id=AMOXICILLIN_ID,
                medication_name="Amoxicillin",
                rxcui="723",
                normalized_name="Amoxicillin",
                confidence=0.95,
            ),
            MedicationGrounding(
                medication_id=METRONIDAZOLE_ID,
                medication_name="Metronidazole",
                rxcui="6922",
                normalized_name="Metronidazole",
                confidence=0.95,
            ),
        ],
        "ddi_warnings": [],
        "degraded": False,
        "needs_llm_parse": False,
    }
