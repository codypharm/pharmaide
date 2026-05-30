"""Validate a production retention approval manifest."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.services.retention_approval_manifest import (
    RetentionApprovalError,
    RetentionApprovalReport,
    manifest_json_example,
    validate_retention_approval_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", help="Path to the JSON manifest.")
    parser.add_argument("--example", action="store_true", help="Print an example manifest.")
    args = parser.parse_args()

    if args.example:
        print(manifest_json_example())
        return 0
    if args.manifest is None:
        parser.error("manifest is required unless --example is used")

    try:
        manifest = json.loads(args.manifest.read_text())
        report = validate_retention_approval_manifest(manifest, Settings())
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        report = RetentionApprovalReport(
            closed_treatment_retention_days=None,
            operational_audit_retention_days=None,
            gcs_lifecycle_retention_days=None,
            cleanup_apply_requested=False,
            errors=(
                RetentionApprovalError(
                    code="manifest_unreadable",
                    message=str(exc),
                ),
            ),
        )

    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
