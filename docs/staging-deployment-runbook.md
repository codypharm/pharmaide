# Staging Deployment Runbook

This runbook is the ordered path for moving PharmaAide from local development
to a Cloud Run staging environment. It coordinates the existing deployment,
auth, queue, storage, WhatsApp, safety-gateway, and evaluation checks.

Use `docs/deployment-readiness-checklist.md` as the detailed checklist for
individual environment variables and verification points.

## 1. Choose Staging Identifiers

Record these before provisioning resources:

- GCP project id.
- Region.
- Backend service name.
- Frontend service or hosting target.
- Database name and connection user.
- Knowledge upload GCS bucket name.
- Cloud Tasks queue names.
- Cloud Tasks invoker service account.
- GCIP/Firebase tenant or project.
- Meta WhatsApp phone number id.
- Staging workspace UUID.

The staging workspace UUID is the key scope used by GCIP claims, knowledge-base
documents, WhatsApp routing, audits, and treatment access.

## 2. Configure GCIP

1. Enable GCIP/Firebase email-password sign-in for staging.
2. Configure MFA policy for pharmacist users.
3. Create or invite staging pharmacist users.
4. Prepare a custom-claims manifest:

```json
{
  "users": [
    {
      "email": "pharmacist@example.com",
      "workspace_id": "11111111-1111-4111-8111-111111111111",
      "workspace_memberships": ["11111111-1111-4111-8111-111111111111"]
    }
  ]
}
```

5. Validate the manifest before applying claims:

```bash
cd backend
uv run python scripts/gcip_claims_manifest.py <claims-manifest.json>
```

6. Apply the validated claims through the approved GCIP/Firebase admin process.
7. Configure backend auth env:

```env
PHARMAIDE_AUTH_MODE=gcip
PHARMAIDE_GCIP_PROJECT_ID=<project-id>
PHARMAIDE_GCIP_WORKSPACE_CLAIM=workspace_id
PHARMAIDE_GCIP_REQUIRE_WORKSPACE_CLAIM=true
PHARMAIDE_GCIP_WORKSPACE_MEMBERSHIPS_CLAIM=workspace_memberships
PHARMAIDE_GCIP_REQUIRE_WORKSPACE_MEMBERSHIP=true
```

8. Configure frontend auth env:

```env
VITE_AUTH_MODE=gcip
VITE_GCIP_API_KEY=<browser-safe-api-key>
VITE_GCIP_AUTH_DOMAIN=<auth-domain>
VITE_GCIP_PROJECT_ID=<project-id>
```

## 3. Provision Database

1. Provision the staging CockroachDB/Postgres-compatible database.
2. Store `PHARMAIDE_DATABASE_URL` in Secret Manager or Cloud Run secret bindings.
3. Run Alembic migrations against staging.
4. Verify:
   - `GET /health`
   - `GET /health/ready`
   - vector column support for `kb_chunks.embedding`

## 4. Provision Knowledge Storage

1. Create the GCS bucket for uploaded knowledge source files.
2. Grant the backend runtime service account read/write/delete access to the
   bucket.
3. Configure object lifecycle rules for the approved retention window.
4. Prepare and validate the storage manifest:

```json
{
  "storage": {
    "backend": "gcs",
    "bucket_name": "pharmaide-kb-prod",
    "prefix": "kb_uploads",
    "max_upload_bytes": 26214400
  },
  "gcs": {
    "runtime_service_account_email": "backend-runtime@<project>.iam.gserviceaccount.com",
    "lifecycle_retention_days": 365,
    "uniform_bucket_level_access": true,
    "public_access_prevention": "enforced"
  }
}
```

```bash
cd backend
uv run python scripts/knowledge_storage_manifest.py <knowledge-storage-manifest.json>
```

5. Configure backend env:

```env
PHARMAIDE_KNOWLEDGE_STORAGE_BACKEND=gcs
PHARMAIDE_KNOWLEDGE_GCS_BUCKET=<bucket>
PHARMAIDE_KNOWLEDGE_GCS_PREFIX=kb_uploads
PHARMAIDE_KNOWLEDGE_MAX_UPLOAD_BYTES=25MB
```

6. After backend deploy, run:

```bash
cd backend
uv run python scripts/knowledge_storage_smoke.py
```

## 5. Deploy Private Safety Gateway

The main backend must not host Llama Guard or AgentDoG models directly.
Deploy them as private services that implement the HTTP contracts in
`docs/safety-provider-gateway.md`.

1. Deploy the Llama Guard-style service.
2. Deploy the AgentDoG/referee-style service.
3. Restrict ingress so only the backend or private network can call them.
4. Configure service authentication, for example a private bearer token or
   service-to-service identity.
5. Prepare and validate the safety gateway manifest:

```json
{
  "environment": "staging",
  "provider": "remote_http",
  "guard": {
    "service": "llama_guard",
    "url": "https://<private-guard-url>/v1/guard/check"
  },
  "referee": {
    "service": "agentdog",
    "url": "https://<private-referee-url>/v1/referee/review"
  },
  "auth": {
    "mode": "bearer_token",
    "secret_name": "projects/<project>/secrets/safety-provider-api-key"
  },
  "network": {
    "ingress": "internal_only",
    "backend_access": "service_identity"
  },
  "timeout_seconds": 10
}
```

```bash
cd backend
uv run python scripts/safety_gateway_manifest.py <safety-gateway-manifest.json>
```

6. Configure backend env:

```env
PHARMAIDE_SAFETY_PROVIDER=remote_http
PHARMAIDE_LLAMA_GUARD_URL=<private-guard-url>
PHARMAIDE_AGENTDOG_URL=<private-referee-url>
PHARMAIDE_SAFETY_PROVIDER_API_KEY=<secret-if-used>
PHARMAIDE_SAFETY_PROVIDER_TIMEOUT_SECONDS=10
```

7. Run:

```bash
cd backend
uv run python scripts/safety_gateway_smoke.py
```

Staging may temporarily use `PHARMAIDE_SAFETY_PROVIDER=model` while the private
gateway is being deployed, but production should target `remote_http`.

## 6. Configure WhatsApp

1. Create or attach the Meta WhatsApp Cloud API app.
2. Configure the staging phone number id.
3. Configure webhook verify token and app secret.
4. Subscribe to inbound message and delivery-status webhook events.
5. Prepare and validate the phone-to-workspace mapping manifest:

```json
{
  "phone_numbers": [
    {
      "phone_number_id": "1234567890",
      "display_phone_number": "+15551234567",
      "workspace_id": "11111111-1111-4111-8111-111111111111"
    }
  ]
}
```

```bash
cd backend
uv run python scripts/whatsapp_workspace_manifest.py <whatsapp-manifest.json>
```

6. Configure backend env:

```env
PHARMAIDE_WHATSAPP_DELIVERY_PROVIDER=cloud_api
PHARMAIDE_WHATSAPP_CLOUD_API_ACCESS_TOKEN=<secret>
PHARMAIDE_WHATSAPP_CLOUD_API_PHONE_NUMBER_ID=<phone-number-id>
PHARMAIDE_WHATSAPP_WORKSPACE_SCOPE_ID=<staging-workspace-uuid>
PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN=<secret>
PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET=<secret>
PHARMAIDE_WHATSAPP_CLOUD_API_VERSION=v25.0
```

7. Webhook URL:

```text
https://<backend-url>/webhooks/whatsapp
```

8. Verify webhook subscription and one test inbound message after a treatment
   cycle is active.

## 7. Configure Cloud Tasks And Scheduler

1. Create Cloud Tasks queues in the backend region.
2. Create the Cloud Tasks invoker service account.
3. Grant that service account permission to invoke the backend Cloud Run
   service.
4. Configure backend env:

```env
PHARMAIDE_INTERNAL_WORKER_AUTH=oidc
PHARMAIDE_INTERNAL_WORKER_AUDIENCE=<backend-cloud-run-url>
PHARMAIDE_TASK_BACKEND=cloud_tasks
PHARMAIDE_CLOUD_TASKS_QUEUE_PATH=projects/<project>/locations/<region>/queues/<queue>
PHARMAIDE_CLOUD_TASKS_BASE_URL=<backend-cloud-run-url>
PHARMAIDE_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL=<service-account-email>
PHARMAIDE_CLOUD_TASKS_OIDC_AUDIENCE=<backend-cloud-run-url>
```

5. Prepare and validate the Cloud Tasks/Scheduler manifest:

```json
{
  "cloud_tasks": {
    "queue_path": "projects/<project>/locations/<region>/queues/<queue>",
    "base_url": "https://<backend-url>",
    "service_account_email": "<service-account-email>",
    "oidc_audience": "https://<backend-url>"
  },
  "scheduler": {
    "pubsub_topic": "projects/<project>/topics/internal-scheduler",
    "push_endpoint": "https://<backend-url>/internal/scheduler/pubsub",
    "push_service_account_email": "<service-account-email>",
    "push_oidc_audience": "https://<backend-url>",
    "dead_letter_topic": "projects/<project>/topics/internal-dead-letter",
    "ticks": [
      {"tick_type": "due_monitoring", "schedule": "*/5 * * * *"},
      {"tick_type": "message_delivery", "schedule": "*/2 * * * *"},
      {"tick_type": "closed_treatment_retention", "schedule": "0 2 * * *"},
      {"tick_type": "knowledge_upload_file_cleanup", "schedule": "0 3 * * *"},
      {"tick_type": "operational_audit_retention", "schedule": "0 4 * * *"}
    ]
  }
}
```

```bash
cd backend
uv run python scripts/cloud_tasks_scheduler_manifest.py <cloud-tasks-manifest.json>
```

6. Configure Cloud Scheduler/PubSub ticks for:
   - due monitoring
   - message delivery
   - closed-treatment retention in dry-run mode first
   - removed upload file cleanup
   - operational audit retention in dry-run mode first
7. Prepare and validate the retention approval manifest before disabling dry-run:

```json
{
  "closed_treatment_retention_days": 365,
  "operational_audit_retention_days": 365,
  "gcs_lifecycle_retention_days": 365,
  "clinical_audit_logs_retained": true,
  "approved_by": {
    "clinical": "Clinical Lead",
    "legal": "Legal Approver",
    "operations": "Operations Lead"
  }
}
```

```bash
cd backend
uv run python scripts/retention_approval_manifest.py <retention-manifest.json>
```

8. Configure dead-letter handling and verify dead-letter audit events.

## 8. Configure Runtime Secrets

Store secrets in Secret Manager or Cloud Run secret bindings:

- `PHARMAIDE_DATABASE_URL`
- `PHARMAIDE_OPENAI_API_KEY`
- `PHARMAIDE_WHATSAPP_CLOUD_API_ACCESS_TOKEN`
- `PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN`
- `PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET`
- `PHARMAIDE_SAFETY_PROVIDER_API_KEY` when used

Do not commit secrets to `.env`, source code, Docker images, or docs.

## 9. Build And Deploy

1. Build backend image from `backend/Dockerfile`.
2. Build frontend image from `frontend/Dockerfile`.
3. Prepare and validate the deployment manifest:

```json
{
  "environment": "staging",
  "project_id": "<project>",
  "region": "<region>",
  "backend": {
    "service_name": "pharmaide-api",
    "image": "<backend-image>@sha256:<digest>",
    "url": "https://<backend-url>",
    "runtime_service_account_email": "backend-runtime@<project>.iam.gserviceaccount.com",
    "min_instances": 0,
    "max_instances": 10,
    "secret_env": {
      "PHARMAIDE_DATABASE_URL": "projects/<project>/secrets/pharmaide-database-url",
      "PHARMAIDE_OPENAI_API_KEY": "projects/<project>/secrets/pharmaide-openai-api-key",
      "PHARMAIDE_WHATSAPP_CLOUD_API_ACCESS_TOKEN": "projects/<project>/secrets/pharmaide-whatsapp-access-token",
      "PHARMAIDE_WHATSAPP_WEBHOOK_VERIFY_TOKEN": "projects/<project>/secrets/pharmaide-whatsapp-verify-token",
      "PHARMAIDE_WHATSAPP_WEBHOOK_APP_SECRET": "projects/<project>/secrets/pharmaide-whatsapp-app-secret"
    }
  },
  "frontend": {
    "service_name": "pharmaide-web",
    "image": "<frontend-image>@sha256:<digest>",
    "url": "https://<frontend-url>",
    "build_env": {
      "VITE_API_BASE_URL": "https://<backend-url>",
      "VITE_AUTH_MODE": "gcip",
      "VITE_GCIP_PROJECT_ID": "<project>"
    }
  },
  "artifact_policy": {
    "image_scanning_required": true,
    "image_signing_required": true
  }
}
```

```bash
cd backend
uv run python scripts/deployment_manifest.py <deployment-manifest.json>
```

4. Deploy backend Cloud Run with production-shaped env and secrets.
5. Deploy frontend with browser-safe `VITE_*` build args.
6. Set backend CORS to the deployed frontend origin:

```env
PHARMAIDE_CORS_ALLOWED_ORIGINS=https://<frontend-url>
PHARMAIDE_LOG_MODE=json
PHARMAIDE_DEBUG_ROUTES_ENABLED=false
```

7. Confirm direct frontend routes load through the SPA fallback.

## 10. Run Release Gates

Before routing real staging users:

```bash
cd backend
uv run ruff check app tests
uv run pytest
uv run python scripts/evaluation_release_gate.py
uv run python scripts/production_preflight.py
uv run python scripts/deployment_manifest.py <deployment-manifest.json>
uv run python scripts/retention_approval_manifest.py <retention-manifest.json>
uv run python scripts/cloud_tasks_scheduler_manifest.py <cloud-tasks-manifest.json>
uv run python scripts/knowledge_storage_manifest.py <knowledge-storage-manifest.json>
uv run python scripts/knowledge_storage_smoke.py
uv run python scripts/safety_gateway_manifest.py <safety-gateway-manifest.json>
uv run python scripts/safety_gateway_smoke.py
```

After deploy:

```bash
cd backend
uv run python scripts/deployment_smoke.py \
  --backend-url https://<backend-cloud-run-url> \
  --frontend-url https://<frontend-url>
```

Optional live provider checks:

```bash
PHARMAIDE_RUN_LIVE_RAG_EVAL=1 uv run pytest tests/evaluations/test_live_rag_products_eval.py -q
PHARMAIDE_RUN_LIVE_LLM=1 PHARMAIDE_OPENAI_API_KEY=... uv run pytest tests/test_analysis_graph.py -q
```

## 11. Manual Product Verification

Use a staging pharmacist account with MFA enabled.

1. Sign in through GCIP.
2. Confirm `/auth/me` returns the expected workspace scope.
3. Upload a clinical asset and confirm it becomes ready.
4. Create a treatment.
5. Confirm analysis auto-starts and completes.
6. Start a monitoring cycle.
7. Confirm a WhatsApp outbound message queues and sends.
8. Send an inbound WhatsApp message from the test patient number.
9. Confirm the message appears in the patient chat.
10. Trigger an unsafe or uncertain patient question.
11. Confirm the draft appears in Triage.
12. Approve or cancel the draft and confirm delivery state updates.
13. Confirm relevant audit rows appear in System Audits.

## 12. Rollback Checks

Before promotion, define rollback actions:

- Previous backend image digest.
- Previous frontend image digest.
- Database migration rollback or restore point decision.
- Cloud Tasks queue pause procedure.
- WhatsApp webhook disable procedure.
- GCIP user disable procedure.
- Safety gateway fallback decision for staging only.

Rollback must not delete clinical audit records. If a rollback requires data
cleanup, run retention endpoints in dry-run mode first and review the audit rows.

## 13. Production Promotion Notes

Promotion from staging to production requires:

- Legal/operations approval of data retention windows.
- Clinical approval of DDI-provider posture and safety-gateway behavior.
- Meta app publishing and production phone readiness.
- Production GCIP users and MFA policy active.
- Production Cloud Tasks/Scheduler and dead-letter verification.
- Release gate and smoke commands passing against production-like credentials.
