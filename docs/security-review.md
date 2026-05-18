# Security Review

Review date: 2026-05-18

This review covers the current pre-production codebase. It does not replace the
remaining production blockers for GCIP, Cloud Run, workspace scoping, or
WhatsApp provider hardening.

## Reviewed Areas

### Secrets

- Backend secrets are loaded through `Settings` and typed as `SecretStr` where
  they are used for OpenAI and safety-provider credentials.
- Frontend API code does not store API keys or patient data in browser storage.
- Production must move secrets from local `.env` files to Google Secret Manager
  or Cloud Run secret bindings.

### CORS

- Current API CORS is restricted to the local Vite origin:
  `http://localhost:5173`.
- Production deployment must replace this with the exact deployed frontend
  origin. Wildcard browser origins are not acceptable for the authenticated app.

### Auth Headers

- `X-Pharmaide-User-Id` is development scaffolding only.
- Production identity must come from GCIP-authenticated claims and workspace
  membership, not from a client-controlled header.
- Knowledge-base scope and treatment access must derive from workspace/clinic
  authorization after auth lands.

### Audit Trails

- Audit payloads are intentionally metadata-oriented: ids, counts, statuses,
  and workflow reasons.
- Patient messages, assistant drafts, medication names, doses, and uploaded
  knowledge excerpts should remain in their clinical/source tables, not audit
  payloads.
- Audit export must stay behind authenticated pharmacist/admin access once auth
  is enabled.

### Data Minimisation

- Conversation text and patient-reported updates are persisted only where they
  are needed for the clinical workflow.
- Course-completion reporting is count-based and avoids copying patient message
  text.
- Uploaded knowledge files are stored as source files plus parsed chunks; delete
  actions remove chunks and the stored source file.
- Production still needs a retention/purge policy for patient data after the
  treatment lifecycle.

## Remaining Production Blockers

The review is complete for the current codebase, but these items remain tracked
as production blockers:

- GCIP authentication and authorization.
- Workspace scoping from clinic/workspace membership.
- HTTPS-only Cloud Run deployment.
- Cloud Tasks/Pub/Sub worker replacement for in-process background work.
- Private safety gateway deployment for Llama Guard / AgentDoG.
