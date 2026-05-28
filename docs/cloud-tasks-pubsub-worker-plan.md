# Cloud Tasks / Pub/Sub Worker Plan

This plan replaces the current in-process `task_runner.schedule(...)` path for
production while keeping it available for local development and tests.

## Goal

Cloud Run instances can stop, restart, or scale to zero. Production background
work must therefore be durable outside process memory. The backend should enqueue
small metadata-only jobs and let Cloud Tasks or Pub/Sub call internal worker
routes that reopen database state by id.

## Current Local Seam

- `app.services.task_runner.schedule(...)` starts an `asyncio` task in-process.
- `task_runner.drain()` waits for local tasks during shutdown.
- Existing callers should remain usable locally while production swaps the
  transport behind the scheduling boundary.

## Transport Choice

Use both services, each for the thing it is best at:

- **Cloud Tasks** for per-resource work that needs retry, dedupe naming, rate
  control, and authenticated HTTP delivery.
- **Cloud Scheduler + Pub/Sub** for periodic ticks that fan into worker routes,
  such as due monitoring and delivery polling.

Every internal worker request must use a service-to-service identity token. The
browser must never call production worker routes directly.

## Job Mapping

| Job | Current entry point | Production trigger | Queue payload | Idempotency key |
| --- | --- | --- | --- | --- |
| Treatment analysis | `analyze_treatment(session_factory, analysis_id, ...)` | Cloud Task after `create_pending_analysis` | `analysis_id`, `kb_scope_id`, config flags only | `analysis:{analysis_id}` |
| Knowledge ingestion | `ingest_document(session_factory, document_id, ...)` | Cloud Task after upload row commit | `document_id` only | `kb-ingest:{document_id}` |
| Buffered patient turn | `process_buffered_patient_messages_for_treatment(...)` | `patient-turn.process` Cloud Task from WhatsApp webhook after debounce | `treatment_id` only | `patient-turn:{treatment_id}:{debounce_bucket}` |
| Due monitoring | `run_due_monitoring(...)` | Cloud Scheduler Pub/Sub tick | `limit`, optional `now` for tests only | service-level schedule tick id |
| Message delivery | `run_message_delivery_once(...)` | Cloud Scheduler Pub/Sub tick or task fanout | `limit` | service-level schedule tick id |
| Closed-treatment retention | `cleanup_closed_treatments(...)` | Cloud Scheduler Pub/Sub tick | none; uses env-configured retention window and dry-run mode | service-level schedule tick id |
| Removed upload file cleanup | `cleanup_removed_upload_files(...)` | Cloud Scheduler Pub/Sub tick | none; scans removed user-upload document rows | service-level schedule tick id |
| Operational audit retention | `cleanup_operational_audit_logs(...)` | Cloud Scheduler Pub/Sub tick | none; uses env-configured retention window and dry-run mode | service-level schedule tick id |

Queue payloads must not include patient message bodies, assistant drafts,
medication names, uploaded document text, or prescription content. Workers load
clinical data from the database by id.

## Worker Routes

The existing internal routes are the production HTTP targets and are protected
by the internal worker auth dependency when
`PHARMAIDE_INTERNAL_WORKER_AUTH=oidc`:

- `POST /internal/treatments/{treatment_id}/run-due-monitoring`
- `POST /internal/monitoring/run-due`
- `POST /internal/message-delivery/run-once`
- `POST /internal/scheduler/pubsub`
- `POST /internal/cleanup/knowledge-upload-files`
- `POST /internal/cleanup/operational-audit-logs`
- `POST /internal/treatments/{treatment_id}/process-buffered-patient-turn`
- `POST /internal/analyses/{analysis_id}/run`
- `POST /internal/knowledge/documents/{document_id}/ingest`

## Idempotency Requirements

Each worker must be safe to retry.

- Analysis: the active-analysis unique constraint already prevents duplicate
  active rows. Completion/failure writes must keep respecting terminal
  `superseded` rows.
- KB ingestion: a removed document must not be resurrected, and retries should
  replace only chunks for the same document while preserving removed/failed
  terminal states.
- Buffered turns: existing buffer claiming prevents duplicate processing for
  messages already claimed by another worker.
- Due monitoring: reminder audit keys prevent duplicate reminder messages for
  the same schedule slot.
- Delivery: queued message ids and provider callback ids prevent duplicate
  state transitions.

## Retry Policy

- Analysis: retry transient worker failures with exponential backoff; mark the
  analysis failed after the final attempt.
- KB ingestion: retry parse/embed/provider errors that are transient; mark the
  document failed after the final attempt.
- Buffered turns: retry worker failures; leave messages unprocessed until a
  successful claim/process cycle.
- Monitoring: retries are safe because reminders are keyed by deterministic
  schedule slots.
- Delivery: retries are safe while status is `queued`; provider failures move
  the message to `failed` for pharmacist/system review.

## Local Development

`task_runner.schedule(...)` remains the default local adapter. Production selects
the Cloud Tasks adapter from settings:

- `PHARMAIDE_TASK_BACKEND=in_process`
- `PHARMAIDE_TASK_BACKEND=cloud_tasks`
- `PHARMAIDE_CLOUD_TASKS_QUEUE_PATH=projects/.../locations/.../queues/...`
- `PHARMAIDE_CLOUD_TASKS_BASE_URL=https://...`
- `PHARMAIDE_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL=...@...iam.gserviceaccount.com`
- `PHARMAIDE_CLOUD_TASKS_OIDC_AUDIENCE=https://...`

The caller contract stays small: schedule a named job plus ids. Production
Cloud Tasks scheduling rejects unnamed coroutine-only work.

The Cloud Tasks backend enqueues metadata-only HTTP tasks for named jobs. It
uses deterministic task names from idempotency keys, so retries and duplicate
route calls converge on the same Cloud Tasks resource instead of fanout.

## Implementation Status

The Cloud Tasks/Pub/Sub worker foundation is implemented:

- Named jobs enqueue metadata-only Cloud Tasks with OIDC-authenticated HTTP targets.
- App startup selects the configured task backend.
- Existing `task_runner.schedule_job(...)` callers delegate to the configured
  backend in production while preserving local in-process test hooks.
- Cloud Scheduler Pub/Sub ticks dispatch due monitoring and message delivery.
- Cloud Scheduler Pub/Sub ticks dispatch closed-treatment retention cleanup in
  configurable dry-run/apply mode.
- Removed knowledge-upload source files can be cleaned through an internal
  endpoint or scheduler tick without exposing titles or storage paths in audits.
- Old operational audit noise can be cleaned through an internal endpoint or
  scheduler tick while clinical/pharmacist decision audit logs remain excluded.
- Internal worker routes can require Google OIDC service-to-service auth.
- Queue retry and dead-letter metadata are audited without storing clinical payloads.
- Buffered patient-turn jobs map to the existing internal processor route with a
  queue-level delay for the debounce window.

Remaining production work is operational: create the queues, grant IAM/OIDC
invoker permissions, configure Cloud Scheduler/Pub/Sub ticks, verify dead-letter
handling, and run the deployment smoke checks against staging.
