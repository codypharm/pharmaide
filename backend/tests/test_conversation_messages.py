"""Provider-neutral conversation turns for Sprint 5 messaging."""

import json
from collections.abc import Mapping
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.safety_provider_factory import ConfiguredSafetyProviders
from app.agents.safety_schemas import GuardRequest, RefereeRequest
from app.db.models import AuditLogEntry, ConversationMessage, Patient, Treatment
from app.services.conversation_messages import submit_patient_conversation_turn


class SequencedGuardProvider:
    def __init__(self, payloads: list[Mapping[str, Any]]) -> None:
        self.payloads = payloads

    async def check(self, request: GuardRequest) -> Mapping[str, Any]:
        return self.payloads.pop(0)


class FakeRefereeProvider:
    async def review(self, request: RefereeRequest) -> Mapping[str, Any]:
        return {
            "action": "allow",
            "violations": [],
            "rationale": "Draft stays within the prescription.",
            "confidence": 0.9,
        }


async def test_submit_patient_turn_records_message_draft_and_non_phi_audit(
    db_session: AsyncSession,
) -> None:
    treatment = await _persist_treatment(db_session)
    providers = ConfiguredSafetyProviders(
        guard_provider=SequencedGuardProvider(
            [
                _guard_payload("input"),
                _guard_payload("output"),
            ]
        ),
        referee_provider=FakeRefereeProvider(),
    )

    turn = await submit_patient_conversation_turn(
        db_session,
        treatment_id=treatment.id,
        patient_message="  Can I take this after food?  ",
        assistant_draft="Please follow the timing your pharmacist approved.",
        prescription_context="Amoxicillin 500 mg three times daily.",
        providers=providers,
    )
    await db_session.flush()

    rows = (
        await db_session.execute(
            select(ConversationMessage).order_by(ConversationMessage.created_at.asc())
        )
    ).scalars().all()
    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "conversation_turn_recorded")
    )

    assert turn.safety_decision.status == "send"
    assert turn.inbound_message.body == "Can I take this after food?"
    assert turn.assistant_message.body == "Please follow the timing your pharmacist approved."
    assert turn.assistant_message.status == "draft_ready"
    assert [(row.direction, row.sender_type, row.status) for row in rows] == [
        ("inbound", "patient", "received"),
        ("outbound", "assistant", "draft_ready"),
    ]
    assert audit is not None
    assert audit.payload == {
        "treatment_id": str(treatment.id),
        "inbound_message_id": str(turn.inbound_message.id),
        "assistant_message_id": str(turn.assistant_message.id),
        "safety_status": "send",
        "hold_reason": None,
    }
    assert "after food" not in json.dumps(audit.payload).lower()


async def test_submit_patient_turn_holds_assistant_draft_when_safety_blocks(
    db_session: AsyncSession,
) -> None:
    treatment = await _persist_treatment(db_session, "CONV-002")
    providers = ConfiguredSafetyProviders(
        guard_provider=SequencedGuardProvider(
            [
                _guard_payload(
                    "input",
                    action="block",
                    categories=["unsafe_medical_advice"],
                ),
            ]
        ),
        referee_provider=FakeRefereeProvider(),
    )

    turn = await submit_patient_conversation_turn(
        db_session,
        treatment_id=treatment.id,
        patient_message="I feel faint after taking extra tablets.",
        assistant_draft="This draft must not be sent.",
        prescription_context="Amoxicillin 500 mg three times daily.",
        providers=providers,
    )
    await db_session.flush()

    assert turn.safety_decision.status == "hold_for_pharmacist"
    assert turn.safety_decision.message_to_send is None
    assert turn.assistant_message.status == "held_for_review"
    assert turn.assistant_message.safety_hold_reason == "input_guard"


async def _persist_treatment(session: AsyncSession, mrn: str = "CONV-001") -> Treatment:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn=mrn,
        phone="+18005551212",
    )
    treatment = Treatment(patient=patient, clinical_objective="Monitor recovery")
    session.add(treatment)
    await session.flush()
    return treatment


def _guard_payload(
    stage: str,
    *,
    action: str = "allow",
    categories: list[str] | None = None,
) -> dict[str, object]:
    return {
        "stage": stage,
        "action": action,
        "categories": categories or [],
        "rationale": f"{stage} guard {action}.",
        "confidence": 0.9,
    }
