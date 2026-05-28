"""Production deployment preflight checks.

Settings validators prove that individual feature toggles have their required
companion values. This module checks the stronger production posture before a
release candidate reaches Cloud Run.
"""

from dataclasses import dataclass
from typing import Literal

from app.config import Settings

PreflightSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class PreflightIssue:
    code: str
    severity: PreflightSeverity
    message: str


@dataclass(frozen=True)
class PreflightReport:
    issues: tuple[PreflightIssue, ...]

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "errors": [
                _issue_dict(issue) for issue in self.issues if issue.severity == "error"
            ],
            "warnings": [
                _issue_dict(issue) for issue in self.issues if issue.severity == "warning"
            ],
        }


def run_production_preflight(settings: Settings) -> PreflightReport:
    """Validate that parsed settings are suitable for production deployment."""
    issues = [
        *_auth_issues(settings),
        *_runtime_issues(settings),
        *_messaging_issues(settings),
        *_storage_issues(settings),
        *_worker_issues(settings),
        *_safety_issues(settings),
        *_retention_issues(settings),
    ]
    return PreflightReport(issues=tuple(issues))


def _auth_issues(settings: Settings) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    _require(
        issues,
        settings.auth_mode == "gcip",
        "auth_mode",
        "Production must use GCIP auth, not local header auth.",
    )
    _require(
        issues,
        settings.gcip_require_workspace_claim,
        "workspace_claim_required",
        "Production must require the GCIP workspace claim.",
    )
    _require(
        issues,
        settings.gcip_require_workspace_membership,
        "workspace_membership_required",
        "Production must require workspace membership claims.",
    )
    return issues


def _runtime_issues(settings: Settings) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    _require(
        issues,
        not settings.debug_routes_enabled,
        "debug_routes",
        "Debug routes must be disabled in production.",
    )
    _require(
        issues,
        settings.log_mode == "json",
        "json_logging",
        "Production logs must use JSON for Cloud Logging.",
    )
    _require(
        issues,
        settings.openai_api_key is not None,
        "openai_api_key",
        "Production analysis, embeddings, and patient reply flows require an OpenAI key.",
    )
    _require(
        issues,
        _has_https_cors_only(settings),
        "cors_https_only",
        "Production CORS origins must be explicit HTTPS URLs.",
    )
    return issues


def _messaging_issues(settings: Settings) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    _require(
        issues,
        settings.whatsapp_delivery_provider == "cloud_api",
        "whatsapp_provider",
        "Production must use WhatsApp Cloud API delivery.",
    )
    _require(
        issues,
        settings.whatsapp_workspace_scope_id is not None,
        "whatsapp_workspace_scope",
        "Production WhatsApp inbound routing must be pinned to a workspace scope.",
    )
    return issues


def _storage_issues(settings: Settings) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    _require(
        issues,
        settings.knowledge_storage_backend == "gcs",
        "knowledge_storage",
        "Production knowledge uploads must use GCS storage.",
    )
    return issues


def _worker_issues(settings: Settings) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    _require(
        issues,
        settings.internal_worker_auth == "oidc",
        "internal_worker_auth",
        "Production internal routes must require OIDC worker auth.",
    )
    _require(
        issues,
        settings.task_backend == "cloud_tasks",
        "task_backend",
        "Production background work must use Cloud Tasks.",
    )
    _require(
        issues,
        _is_https(settings.cloud_tasks_base_url),
        "cloud_tasks_base_url",
        "Cloud Tasks base URL must be HTTPS.",
    )
    _require(
        issues,
        _is_https(settings.cloud_tasks_oidc_audience),
        "cloud_tasks_oidc_audience",
        "Cloud Tasks OIDC audience must be HTTPS.",
    )
    return issues


def _safety_issues(settings: Settings) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    _require(
        issues,
        settings.safety_provider == "remote_http",
        "safety_provider",
        "Production must use the private Llama Guard / AgentDoG safety gateway.",
    )
    return issues


def _retention_issues(settings: Settings) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    _warn(
        issues,
        not settings.data_retention_cleanup_dry_run,
        "data_retention_dry_run",
        "Treatment data retention cleanup is still in dry-run mode.",
    )
    _warn(
        issues,
        not settings.audit_retention_cleanup_dry_run,
        "audit_retention_dry_run",
        "Operational audit retention cleanup is still in dry-run mode.",
    )
    return issues


def _require(
    issues: list[PreflightIssue],
    condition: bool,
    code: str,
    message: str,
) -> None:
    if not condition:
        issues.append(PreflightIssue(code=code, severity="error", message=message))


def _warn(
    issues: list[PreflightIssue],
    condition: bool,
    code: str,
    message: str,
) -> None:
    if not condition:
        issues.append(PreflightIssue(code=code, severity="warning", message=message))


def _has_https_cors_only(settings: Settings) -> bool:
    origins = settings.cors_allowed_origin_list
    return bool(origins) and all(_is_https(origin) for origin in origins)


def _is_https(value: str | None) -> bool:
    return bool(value and value.startswith("https://"))


def _issue_dict(issue: PreflightIssue) -> dict[str, str]:
    return {
        "code": issue.code,
        "message": issue.message,
    }
