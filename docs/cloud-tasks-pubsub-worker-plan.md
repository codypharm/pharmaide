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
| Buffered patient turn | `process_buffered_patient_messages_for_treatment(...)` | Cloud Task from WhatsApp webhook after debounce | `treatment_id` only | `patient-turn:{treatment_id}:{debounce_bucket}` |
| Due monitoring | `run_due_monitoring(...)` | Cloud Scheduler Pub/Sub tick | `limit`, optional `now` for tests only | service-level schedule tick id |
| Message delivery | `run_message_delivery_once(...)` | Cloud Scheduler Pub/Sub tick or task fanout | `limit` | service-level schedule tick id |

Queue payloads must not include patient message bodies, assistant drafts,
medication names, uploaded document text, or prescription content. Workers load
clinical data from the database by id.

## Worker Routes

Keep the existing local/internal routes as the production HTTP targets, then add
auth protection before deployment:

- `POST /internal/treatments/{treatment_id}/run-due-monitoring`
- `POST /internal/monitoring/run-due`
- `POST /internal/message-delivery/run-once`
- `POST /internal/treatments/{treatment_id}/process-buffered-patient-turn`

Add these production-only routes when the queue adapter lands:

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

Keep `task_runner.schedule(...)` as the default local adapter. Production should
select a queue adapter from settings, for example:

- `PHARMAIDE_TASK_BACKEND=in_process`
- `PHARMAIDE_TASK_BACKEND=cloud_tasks`

The caller contract should stay small: schedule a named job plus ids. Avoid
passing coroutine objects through the production adapter.

## Suggested Implementation Slices

1. Replace the KB upload direct `task_runner.schedule(...)` call with named job
   scheduling.
2. Add internal worker routes for analysis and KB ingestion.
3. Add Cloud Tasks adapter with OIDC-authenticated HTTP targets.
4. Add Cloud Scheduler/Pub/Sub ticks for due monitoring and delivery.
5. Add queue retry/dead-letter audit events without PHI.
