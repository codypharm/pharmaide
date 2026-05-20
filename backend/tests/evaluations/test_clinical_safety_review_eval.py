"""Deterministic clinical-safety review evaluation cases.

These evals pin the analysis-time boundary: model-backed safety review may only
surface interactions between current treatment medications, or substances the
patient explicitly reported. General label examples must not appear as if they
were active regimen interactions.
"""

import pytest
from pydantic_ai.models.test import TestModel

from app.agents.analysis_schemas import AnalysisState
from app.agents.nodes.clinical_safety_review import (
    build_clinical_safety_agent,
    review_clinical_safety,
)

pytestmark = pytest.mark.clinical_eval


async def test_clinical_safety_review_eval_filters_off_regimen_interaction_examples() -> None:
    agent = build_clinical_safety_agent(
        model=TestModel(
            custom_output_args={
                "source_type": "model_review",
                "possible_interactions": [
                    "Amoxicillin + metronidazole: overlapping gastrointestinal effects.",
                    "Metronidazole + warfarin: may increase anticoagulant effect.",
                    "Metronidazole + lithium: possible lithium toxicity.",
                    "Metronidazole + disulfiram: neuropsychiatric reaction risk.",
                    "Metronidazole + alcohol: reaction risk.",
                ],
                "monitoring_concerns": [],
                "counseling_points": [],
                "missing_information": [],
                "confidence": 0.62,
                "requires_pharmacist_review": True,
            }
        )
    )

    reviewed = await review_clinical_safety(_amoxicillin_metronidazole_state(), agent=agent)

    assert reviewed["clinical_safety_review"] is not None
    assert reviewed["clinical_safety_review"].possible_interactions == [
        "Amoxicillin + metronidazole: overlapping gastrointestinal effects."
    ]


def _amoxicillin_metronidazole_state() -> AnalysisState:
    return {
        "medications": [
            {
                "id": "00000000-0000-4000-8000-000000000001",
                "name": "Amoxicillin",
                "dosage": "1 g",
                "frequency": "Twice Daily (BID)",
                "duration": "14 days",
                "objective": None,
            },
            {
                "id": "00000000-0000-4000-8000-000000000002",
                "name": "Metronidazole",
                "dosage": "400 mg",
                "frequency": "Three Times Daily (TID)",
                "duration": "7 days",
                "objective": None,
            },
        ],
        "groundings": [],
        "ddi_warnings": [],
        "degraded": False,
    }
