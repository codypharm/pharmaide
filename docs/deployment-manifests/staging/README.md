# Staging Deployment Manifests

These JSON files are the staging rollout inputs referenced by the deployment
runbook. They intentionally contain deployment metadata and Secret Manager
resource names only, never raw secrets.

Replace the placeholder project, domain, phone, user, workspace, image digest,
and service-account values with the real staging values before applying any
cloud changes.

Validate from `backend/`:

```bash
uv run python scripts/gcip_claims_manifest.py ../docs/deployment-manifests/staging/claims-manifest.json
uv run python scripts/whatsapp_workspace_manifest.py ../docs/deployment-manifests/staging/whatsapp-manifest.json
uv run python scripts/knowledge_storage_manifest.py ../docs/deployment-manifests/staging/knowledge-storage-manifest.json
uv run python scripts/cloud_tasks_scheduler_manifest.py ../docs/deployment-manifests/staging/cloud-tasks-manifest.json
uv run python scripts/safety_gateway_manifest.py ../docs/deployment-manifests/staging/safety-gateway-manifest.json
uv run python scripts/retention_approval_manifest.py ../docs/deployment-manifests/staging/retention-manifest.json
uv run python scripts/deployment_manifest.py ../docs/deployment-manifests/staging/deployment-manifest.json
```
