# Production Readiness Roadmap

This file tracks the remaining work that must survive sprint-plan cleanup.
Keep each item as a small, reviewable slice.

## Core Production Blockers

- WhatsApp integration: inbound webhook, outbound provider, delivery callbacks, and message buffering for multi-message patient bursts.
- GCIP authentication: login/session enforcement, MFA, user identity propagation, and replacement of pre-auth `X-Pharmaide-User-Id` scaffolding.
- Workspace scoping: derive clinical and knowledge-base scope from the pharmacist's clinic/workspace, not from the patient.
- GCP deployment: Cloud Run containers, production environment variables, secrets, HTTPS-only browser-to-API path, and deployment runbooks.
- Cloud Tasks/Pub/Sub operations: replace the in-process task runner before production scheduling and WhatsApp processing.
- Private safety gateway: deploy Llama Guard / AgentDoG behind backend-only provider adapters with fail-closed behavior.
- Evaluation suite: run clinical, safety, retrieval, DDI, and patient-message regression cases before production release.

## Product Completion

- Real WhatsApp scheduled check-ins and adherence capture.
- Existing-treatment medication changes: add/edit medication workflow and pharmacist UI for stale analysis/schedule rerun after regimen changes.
- Buffered-message worker integration: connect the internal processing seam to Cloud Tasks/Pub/Sub once deployment infrastructure is available.
- Buffered-message operator visibility: expose processing/retry state only where pharmacists need it, without showing queue internals in routine chat UI.
- Silence/non-response handling for missed check-ins.
- Production audit coverage review for remaining clinical, delivery, and infrastructure actions.
- Licensed DDI provider replacement when Lexicomp, DrugBank, or another approved source is available.

## Global Standard Checklist

- Behavioral nudging for patient adherence, while preserving safety boundaries.
- Privacy mode hardening and PHI masking review.
- Workspace isolation tests.
- Safety failure-mode tests for guard timeouts, invalid safety output, and provider outage.
- Delivery failure-mode tests for WhatsApp retries and provider callback mismatch.
- Scheduling failure-mode tests for delayed tasks, duplicate triggers, and course completion.
- Security review for secrets, CORS, auth headers, audit trails, and data minimisation.
