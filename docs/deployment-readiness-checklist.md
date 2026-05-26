# Deployment Readiness Checklist

This is the pre-deployment checklist for moving PharmaAide from local
development toward a Cloud Run staging environment. It is not a production
approval checklist; Cloud Run rollout, durable storage, queue operations,
provider deployments, and evaluations are still tracked as production blockers.

## Deployment Targets

- Backend: GCP Cloud Run service running the FastAPI app.
- Frontend: static Vite build served from the chosen hosting layer.
- Database: CockroachDB/Postgres-compatible database reachable from Cloud Run.
- Queueing: Cloud Tasks for internal worker jobs.
- Messaging: Meta WhatsApp Cloud API and webhook.
- Secrets: Google Secret Manager or Cloud Run secret bindings.

## Backend Environment

Required for staging:

- `PHARMAIDE_DATABASE_URL`: async SQLAlchemy database URL.
- `PHARMAIDE_OPENAI_API_KEY`: OpenAI key for agents, embeddings, and interim
  model safety checks.
- `PHARMAIDE_CORS_ALLOWED_ORIGINS`: comma-separated deployed frontend origins.
- `PHARMAIDE_AUTH_MODE=gcip`: require GCIP/Firebase ID tokens.
- `PHARMAIDE_GCIP_PROJECT_ID`: GCIP/Firebase project ID used as token audience.
- `PHARMAIDE_GCIP_WORKSPACE_CLAIM=workspace_id`: GCIP custom claim carrying the
  pharmacist workspace/clinic UUID used for knowledge-base scope.
- `PHARMAIDE_GCIP_REQUIRE_WORKSPACE_CLAIM=true`: enable after GCIP custom claims
  are configured so production requests without workspace scope fail closed.
- `PHARMAIDE_GCIP_WORKSPACE_MEMBERSHIPS_CLAIM=workspace_memberships`: GCIP
  custom claim containing the workspace UUIDs this pharmacist may access.
- `PHARMAIDE_GCIP_REQUIRE_WORKSPACE_MEMBERSHIP=true`: enable after membership
  claims are issued so verified users cannot access unassigned workspaces.
- `PHARMAIDE_LOG_MODE=json`: structured logs for Cloud Run.
- `PHARMAIDE_DEBUG_ROUTES_ENABLED=false`: debug graph route must stay unmounted.
- `PHARMAIDE_RXNORM_BASE_URL=https://rxnav.nlm.nih.gov/REST`.
- `PHARMAIDE_ANALYSIS_TIMEOUT_SECONDS=60` or another reviewed value.
- `PHARMAIDE_MAX_CONCURRENT_ANALYSES_PER_USER=3` or another reviewed value.

Knowledge-base settings:

- `PHARMAIDE_KNOWLEDGE_MAX_UPLOAD_BYTES=25MB` or another reviewed cap.
- `PHARMAIDE_KNOWLEDGE_INGESTION_STALE_MINUTES=30`.
- `PHARMAIDE_KNOWLEDGE_UPLOAD_DIR` configures the local-development storage
  adapter. Before production, switch the storage adapter to durable object/blob
  storage.
- `PHARMAIDE_DATA_RETENTION_CLOSED_TREATMENT_DAYS=365` or another reviewed
  archive-gated retention window.

WhatsApp settings:

- `PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN`: Meta webhook verify token.
- `PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET`: Meta app secret for POST signature
  validation.
- `PHARMAIDE_WHATSAPP_DELIVERY_PROVIDER=cloud_api`.
- `PHARMAIDE_WHATSAPP_CLOUD_API_ACCESS_TOKEN`: Meta Cloud API access token.
- `PHARMAIDE_WHATSAPP_CLOUD_API_PHONE_NUMBER_ID`: sender phone number ID.
- `PHARMAIDE_WHATSAPP_WORKSPACE_SCOPE_ID`: optional workspace UUID for this
  sender number; set it when one Meta phone number is assigned to one clinic so
  inbound messages route only inside that workspace.
- `PHARMAIDE_WHATSAPP_CLOUD_API_VERSION=v25.0`.
- `PHARMAIDE_WHATSAPP_CLOUD_API_BASE_URL=https://graph.facebook.com`.

Internal worker and queue settings:

- `PHARMAIDE_INTERNAL_WORKER_AUTH=oidc`.
- `PHARMAIDE_INTERNAL_WORKER_AUDIENCE`: expected OIDC audience for internal
  route calls.
- `PHARMAIDE_TASK_BACKEND=cloud_tasks`.
- `PHARMAIDE_CLOUD_TASKS_QUEUE_PATH`: `projects/<project>/locations/<region>/queues/<queue>`.
- `PHARMAIDE_CLOUD_TASKS_BASE_URL`: backend Cloud Run HTTPS base URL.
- `PHARMAIDE_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL`: Cloud Tasks invoker service
  account.
- `PHARMAIDE_CLOUD_TASKS_OIDC_AUDIENCE`: usually the backend Cloud Run URL.

Safety settings:

- Staging can run with `PHARMAIDE_SAFETY_PROVIDER=model`.
- Production target is `PHARMAIDE_SAFETY_PROVIDER=remote_http`.
- Remote safety mode requires:
  - `PHARMAIDE_LLAMA_GUARD_URL`
  - `PHARMAIDE_AGENTDOG_URL`
  - optional `PHARMAIDE_SAFETY_PROVIDER_API_KEY`

## Frontend Environment

- `VITE_API_BASE_URL`: backend Cloud Run HTTPS base URL.
- `VITE_AUTH_MODE=gcip`: enable browser sign-in flow with Firebase/GCIP ID
  tokens. Frontend sessions use memory-only Firebase persistence.
- `VITE_GCIP_API_KEY`, `VITE_GCIP_AUTH_DOMAIN`, `VITE_GCIP_PROJECT_ID`:
  browser-safe Firebase/GCIP client configuration.
- Frontend builds must not contain secret values. Only browser-safe public
  configuration belongs in `VITE_*` variables.

## Database And Migrations

- Run Alembic migrations against the staging database before routing traffic.
- Verify vector support for `kb_chunks.embedding`.
- Verify all expected tables exist:
  - treatments and medications
  - treatment analyses
  - adherence events and patient check-ins
  - conversation/triage/message delivery tables
  - knowledge documents/chunks
  - audit log entries
- Run a smoke test that creates a treatment, analyzes it, starts monitoring,
  sends a queued message, and records an audit event.

## Cloud Tasks And Internal Workers

- Create Cloud Tasks queues in the same region as the backend where practical.
- Grant the Cloud Tasks service account permission to invoke the backend Cloud
  Run service.
- Configure OIDC tokens for internal route calls.
- Verify these internal flows:
  - analysis run
  - due monitoring run
  - buffered patient turn processing
  - message delivery run
  - stale ingestion cleanup
  - closed-treatment retention cleanup in dry-run mode before any apply run
  - dead-letter audit recording
- Confirm retry headers are audited without request bodies.

## WhatsApp Webhook

- Webhook URL: `https://<backend>/webhooks/whatsapp`.
- Configure Meta verify token to match
  `PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
- Configure app secret to match `PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET`.
- Subscribe to the WhatsApp Business Account message events required for:
  - inbound messages
  - delivery status callbacks
- Verify:
  - GET verification succeeds.
  - POST signature validation succeeds.
  - If `PHARMAIDE_WHATSAPP_WORKSPACE_SCOPE_ID` is set, inbound phone matching is
    limited to that workspace.
  - inbound message is buffered only when there is one active treatment for the
    sender phone.
  - delivery status updates queued/sent/failed messages.

## Current Deployment Blockers

- GCIP login/session enforcement, workspace claims, and membership-claim checks
  exist. Remaining auth work is MFA policy setup, production user provisioning
  and custom-claim issuance, plus a final route audit for local/dev scope
  assumptions.
- WhatsApp Cloud API delivery, signed webhooks, and optional workspace-scoped
  inbound routing exist. Remaining messaging work is Meta app publishing,
  production phone setup, event subscriptions, and phone-to-workspace mapping
  rollout.
- Knowledge upload source files are behind a storage adapter but still use the
  local-disk implementation.
- Archive-gated treatment/patient/conversation purge exists behind an internal
  dry-run-first endpoint. Remaining retention work is production scheduling,
  source-file/object cleanup, and final legal retention-window approval.
- Cloud Tasks code support exists, but queues, IAM/OIDC, scheduler ticks, and
  dead-letter operations still need real GCP deployment verification.
- Private Llama Guard / AgentDoG HTTP adapters exist, but the gateway services
  are not yet deployed.
- Clinical, safety, retrieval, DDI, and patient-message evaluations still need
  to be run as a release gate.

## Pre-Staging Verification

Run before deploying a staging candidate:

```bash
cd backend
uv run ruff check app tests
uv run pytest
```

Optional live checks:

```bash
PHARMAIDE_RUN_LIVE_RAG_EVAL=1 uv run pytest tests/evaluations/test_live_rag_products_eval.py -q
PHARMAIDE_RUN_LIVE_LLM=1 PHARMAIDE_OPENAI_API_KEY=... uv run pytest tests/test_analysis_graph.py -q
```

Then verify manually in the UI:

- Create treatment.
- Analysis auto-starts and completes.
- Monitoring cycle can start.
- WhatsApp outbound message queues and sends.
- Inbound WhatsApp message appears in patient chat for the active treatment.
- Unsafe/uncertain AI draft appears in Triage and can be approved/canceled.
- Audit page records the relevant workflow events.
