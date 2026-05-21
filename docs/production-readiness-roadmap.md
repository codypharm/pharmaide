# Production Readiness Roadmap

This file tracks the remaining work that must survive sprint-plan cleanup.
Keep each item as a small, reviewable slice.

## Core Production Blockers

- WhatsApp integration: workspace-aware phone routing once GCIP/workspaces land.
- GCIP authentication: frontend login/session enforcement, MFA, user identity
  propagation, and route-by-route replacement of pre-auth
  `X-Pharmaide-User-Id` scaffolding.
- Workspace scoping: derive clinical and knowledge-base scope from the pharmacist's clinic/workspace, not from the patient.
- GCP deployment: Cloud Run containers, production environment variables,
  secrets, HTTPS-only browser-to-API path, and deployment runbooks. See
  `docs/deployment-readiness-checklist.md`.
- Cloud Tasks/Pub/Sub operations: deploy and verify the implemented queue
  foundation with real GCP queues, Cloud Scheduler/Pub/Sub ticks, IAM/OIDC
  invokers, dead-letter handling, and operational runbooks. See
  `docs/cloud-tasks-pubsub-worker-plan.md`.
- Private safety gateway: deploy Llama Guard / AgentDoG behind backend-only provider adapters with fail-closed behavior.
- Evaluation suite: run clinical, safety, retrieval, DDI, and patient-message regression cases before production release.

## Product Completion

- Licensed DDI provider replacement when Lexicomp, DrugBank, or another approved source is available.
