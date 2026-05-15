"""Non-PHI audit rows for safety sandwich decisions."""

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.safety_schemas import (
    GuardResult,
    RefereeResult,
    RefereeViolation,
    SafetyReview,
)
from app.db.models import AuditLogEntry
from app.services.safety_audit import audit_safety_review


async def test_audit_safety_review_writes_non_phi_payload(db_session: AsyncSession) -> None:
    treatment_id = uuid4()
    review = SafetyReview(
        treatment_id=treatment_id,
        input_guard=GuardResult(
            stage="input",
            action="allow",
            categories=[],
            rationale="Patient asked about a dose. Do not persist this.",
            confidence=0.91,
        ),
        referee=RefereeResult(
            action="block",
            violations=[
                RefereeViolation(
                    violation_type="dosage_change",
                    description="Draft said to take two tablets. Do not persist this.",
                )
            ],
            rationale="Draft changed dosage. Do not persist this.",
            confidence=0.95,
        ),
        output_guard=GuardResult(
            stage="output",
            action="block",
            categories=["unsafe_medical_advice"],
            rationale="Output guard was skipped. Do not persist this.",
            confidence=0,
        ),
    )

    await audit_safety_review(db_session, review)
    await db_session.flush()

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "safety_review_completed")
    )

    assert audit is not None
    assert audit.resource_type == "treatment"
    assert audit.resource_id == treatment_id
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "input_action": "allow",
        "input_categories": [],
        "referee_action": "block",
        "referee_violation_types": ["dosage_change"],
        "output_action": "block",
        "output_categories": ["unsafe_medical_advice"],
        "requires_pharmacist_review": True,
    }
    serialized = json.dumps(audit.payload)
    assert "Patient asked about a dose" not in serialized
    assert "take two tablets" not in serialized
    assert "changed dosage" not in serialized
