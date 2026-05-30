"""Validate a WhatsApp phone-to-workspace rollout manifest."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.services.whatsapp_workspace_manifest import (
    WhatsAppWorkspaceManifestError,
    WhatsAppWorkspaceManifestReport,
    validate_whatsapp_workspace_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to the JSON WhatsApp manifest.")
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text())
        report = validate_whatsapp_workspace_manifest(manifest, Settings())
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        report = WhatsAppWorkspaceManifestReport(
            phone_numbers=(),
            errors=(
                WhatsAppWorkspaceManifestError(
                    index=None,
                    phone_number_id=None,
                    code="manifest_unreadable",
                    message=str(exc),
                ),
            ),
        )

    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
