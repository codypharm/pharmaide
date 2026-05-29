# Production Readiness Roadmap

This file tracks the remaining work that must survive sprint-plan cleanup.
Keep each item as a small, reviewable slice.

## Core Production Blockers

- Auth and workspace readiness: GCIP login/session enforcement, `/auth/me`,
  workspace claims, and workspace-membership claim checks are implemented.
  The route-level guard audit is covered by regression tests. Remaining work is
  GCIP MFA policy setup and production user provisioning/custom claims.
- WhatsApp production readiness: Cloud API delivery, signed webhook handling,
  delivery callbacks, workspace-scoped inbound routing, and active-treatment
  routing are implemented locally. Remaining work is Meta app publishing,
  production phone setup, webhook event subscriptions, and operational rollout
  of the phone-to-workspace mapping.
- GCP deployment: backend Cloud Run container artifact, production environment
  variables, secrets, HTTPS-only browser-to-API path, and deployment runbooks.
  Backend and frontend Dockerfiles exist. A pre-deploy production preflight
  command validates deployment posture, and a post-deploy smoke command checks
  liveness/readiness/frontend reachability. Remaining work is real Cloud Run
  deployment execution, image scanning/signing policy, and HTTPS domain rollout.
  See `docs/deployment-readiness-checklist.md`.
- Cloud Tasks/Pub/Sub operations: Cloud Tasks enqueue support and internal
  worker routes are implemented. Remaining work is deploying and verifying real
  GCP queues, Cloud Scheduler/Pub/Sub ticks, IAM/OIDC invokers, dead-letter
  handling, and operational runbooks. See
  `docs/cloud-tasks-pubsub-worker-plan.md`.
- Knowledge source storage: uploaded source files are behind local and GCS
  storage adapters. A storage smoke command verifies write/read/delete against
  the configured adapter. Remaining work is provisioning the production bucket,
  IAM, lifecycle rules, and running deployment verification.
- Data retention: archive-gated treatment/patient/conversation purge is
  implemented behind an internal dry-run-first endpoint and scheduler tick.
  Removed upload file cleanup is implemented behind an internal endpoint and
  scheduler tick. Operational audit retention is implemented for low-risk
  system audit rows only. Remaining work is production Cloud Scheduler
  configuration, production bucket lifecycle policy verification, clinical
  audit retention policy approval, and final legal retention-window approval.
- Private safety gateway: deploy Llama Guard / AgentDoG behind backend-only provider adapters with fail-closed behavior.
- Evaluation suite: deterministic clinical, safety, retrieval, DDI, and
  patient-message regression cases are wrapped by
  `scripts/evaluation_release_gate.py`. Remaining work is running the gate on
  each release candidate and running optional live provider evals with
  production-like credentials.

## Product Completion

- Licensed DDI provider replacement when Lexicomp, DrugBank, or another approved source is available.
