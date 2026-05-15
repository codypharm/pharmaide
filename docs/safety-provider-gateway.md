# Safety Provider Gateway

PharmaAide's main backend should not host Llama Guard or AgentDoG models
directly in production. The backend calls provider adapters; the adapters call
a private safety gateway. This keeps model-serving dependencies, GPU/runtime
needs, and provider outages isolated from the main API.

## Runtime Modes

- `PHARMAIDE_SAFETY_PROVIDER=model`
  - Uses the in-app PydanticAI fallback providers.
  - Requires `PHARMAIDE_OPENAI_API_KEY`.
  - Intended for development and interim deployments.

- `PHARMAIDE_SAFETY_PROVIDER=remote_http`
  - Calls private HTTP endpoints for Llama Guard-style and AgentDoG-style checks.
  - Requires `PHARMAIDE_LLAMA_GUARD_URL` and `PHARMAIDE_AGENTDOG_URL`.
  - Optional `PHARMAIDE_SAFETY_PROVIDER_API_KEY` is sent as a bearer token.
  - Remote failures fail closed. They do not fall back to the in-app model.

- `PHARMAIDE_SAFETY_PROVIDER=unconfigured`
  - Always fails closed and holds patient-facing drafts for pharmacist review.

## HTTP Contract

### Guard Check

`POST /v1/guard/check`

Request body:

```json
{
  "stage": "input",
  "treatment_id": "11111111-1111-1111-1111-111111111111",
  "actor_role": "patient",
  "content": "Can I take this after food?"
}
```

Response body:

```json
{
  "stage": "input",
  "action": "allow",
  "categories": [],
  "rationale": "Safe adherence question.",
  "confidence": 0.88,
  "safe_response": null,
  "requires_pharmacist_review": false
}
```

### Referee Review

`POST /v1/referee/review`

Request body:

```json
{
  "treatment_id": "11111111-1111-1111-1111-111111111111",
  "patient_message": "Can I take more?",
  "assistant_draft": "Take two tablets tonight.",
  "prescription_context": "Lisinopril 10 mg once daily."
}
```

Response body:

```json
{
  "action": "block",
  "violations": [
    {
      "violation_type": "dosage_change",
      "description": "Draft changes the approved dose."
    }
  ],
  "rationale": "Draft changes treatment instructions.",
  "confidence": 0.93,
  "safe_response": null,
  "requires_pharmacist_review": true
}
```

## Failure Policy

Remote safety provider failures are safety failures. Timeouts, 5xx responses,
non-JSON responses, or schema-invalid responses must hold the draft for
pharmacist review. The backend must not silently downgrade from `remote_http`
to `model` because that would weaken the configured production safety boundary.

## Future gRPC Path

The current HTTP adapter is intentionally behind provider protocols. A future
`remote_grpc` adapter can implement the same `SafetyGuardProvider` and
`SafetyRefereeProvider` interfaces without changing the safety sandwich or
patient-safety service.
