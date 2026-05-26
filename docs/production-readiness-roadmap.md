# Production Readiness Roadmap

This file tracks the remaining work that must survive sprint-plan cleanup.
Keep each item as a small, reviewable slice.

## Core Production Blockers

- Auth and workspace readiness: GCIP login/session enforcement, `/auth/me`,
  workspace claims, and workspace-membership claim checks are implemented.
  Remaining work is GCIP MFA policy setup, production user provisioning/custom
  claims, and a final route audit to remove local/dev scope assumptions.
- WhatsApp production readiness: Cloud API delivery, signed webhook handling,
  delivery callbacks, workspace-scoped inbound routing, and active-treatment
  routing are implemented locally. Remaining work is Meta app publishing,
  production phone setup, webhook event subscriptions, and operational rollout
  of the phone-to-workspace mapping.
- GCP deployment: Cloud Run containers, production environment variables,
  secrets, HTTPS-only browser-to-API path, and deployment runbooks. See
  `docs/deployment-readiness-checklist.md`.
- Cloud Tasks/Pub/Sub operations: deploy and verify the implemented queue
  foundation with real GCP queues, Cloud Scheduler/Pub/Sub ticks, IAM/OIDC
  invokers, dead-letter handling, and operational runbooks. See
  `docs/cloud-tasks-pubsub-worker-plan.md`.
- Knowledge source storage: uploaded source files still use local disk; replace
  with durable object/blob storage before production.
- Data retention: archive-gated treatment/patient/conversation purge is
  implemented behind an internal dry-run-first endpoint. Remaining work is
  production scheduling, uploaded-source object cleanup, broader audit retention
  policy, and final legal retention-window approval.
- Private safety gateway: deploy Llama Guard / AgentDoG behind backend-only provider adapters with fail-closed behavior.
- Evaluation suite: run clinical, safety, retrieval, DDI, and patient-message regression cases before production release.

## Product Completion

- Licensed DDI provider replacement when Lexicomp, DrugBank, or another approved source is available.
