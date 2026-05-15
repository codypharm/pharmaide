"""Audit helpers for safety sandwich decisions.

Safety review payloads can contain patient messages, assistant drafts, and
prescription context. Audit rows must keep only minimum non-PHI decision
metadata so downstream forensics can prove the safety layer ran.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.safety_sandwich import can_send_to_patient
from app.agents.safety_schemas import SafetyReview
from app.db.models import AuditLogEntry


async def audit_safety_review(session: AsyncSession, review: SafetyReview) -> None:
    """Write a non-PHI audit row for a completed safety sandwich review."""
    session.add(
        AuditLogEntry(
            event_type="safety_review_completed",
            resource_type="treatment",
            resource_id=review.treatment_id,
            payload={
                "treatment_id": str(review.treatment_id),
                "input_action": review.input_guard.action,
                "input_categories": review.input_guard.categories,
                "referee_action": review.referee.action,
                "referee_violation_types": [
                    violation.violation_type for violation in review.referee.violations
                ],
                "output_action": review.output_guard.action,
                "output_categories": review.output_guard.categories,
                "requires_pharmacist_review": not can_send_to_patient(review),
            },
        )
    )
