# Security Review

Review date: 2026-05-18

This review covers the current pre-production codebase. It does not replace the
remaining production blockers for Cloud Run, durable storage, queue operations,
provider deployments, or release-gate evaluations.

## Reviewed Areas

### Secrets

- Backend secrets are loaded through `Settings` and typed as `SecretStr` where
  they are used for OpenAI and safety-provider credentials.
- Frontend API code does not store API keys or patient data in browser storage.
- GCIP browser sessions use Firebase memory-only persistence so ID tokens are
  not kept in durable browser storage.
- Production must move secrets from local `.env` files to Google Secret Manager
  or Cloud Run secret bindings.

### CORS

- Current API CORS is restricted to the local Vite origin:
  `http://localhost:5173`.
- Production deployment must replace this with the exact deployed frontend
  origin. Wildcard browser origins are not acceptable for the authenticated app.

### Auth Headers

- `X-Pharmaide-User-Id` is development scaffolding only.
- Production identity comes from GCIP-authenticated claims when
  `PHARMAIDE_AUTH_MODE=gcip`.
- Workspace/clinic scope is derived from the verified workspace claim, and can
  be fail-closed against a workspace-membership claim.
- Remaining auth hardening is MFA policy setup, production user provisioning,
  and custom-claim issuance. Route-level guard coverage is enforced by
  regression tests.

### Audit Trails

- Audit payloads are intentionally metadata-oriented: ids, counts, statuses,
  and workflow reasons.
- Patient messages, assistant drafts, medication names, doses, and uploaded
  knowledge excerpts should remain in their clinical/source tables, not audit
  payloads.
- Audit export is behind the authenticated pharmacist route dependency; add
  admin/role separation before exposing multi-workspace admin views.

### Data Minimisation

- Conversation text and patient-reported updates are persisted only where they
  are needed for the clinical workflow.
- Course-completion reporting is count-based and avoids copying patient message
  text.
- Uploaded knowledge files are stored as source files plus parsed chunks; delete
  actions remove chunks and the stored source file.
- Archive-gated treatment retention, removed upload file cleanup, and
  operational audit retention exist behind internal dry-run-first paths.
  Production still needs scheduled rollout, durable object-storage lifecycle
  cleanup, clinical audit retention approval, and final legal retention windows.

## Remaining Production Blockers

The review is complete for the current codebase, but these items remain tracked
as production blockers:

- GCIP MFA policy setup, production user provisioning, and custom-claim issuance.
- HTTPS-only Cloud Run deployment.
- Production GCS bucket provisioning, IAM, and lifecycle rules for uploaded
  knowledge source files.
- Retention rollout for scheduled cleanup, production bucket lifecycle policy
  verification, clinical audit retention approval, and final legal retention
  windows.
- Cloud Tasks/Pub/Sub deployment and IAM/OIDC verification for background work.
- Private safety gateway deployment for Llama Guard / AgentDoG.
- Release-gate evaluations for clinical, safety, retrieval, DDI, and patient-message behavior.
