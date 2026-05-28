"""Run deployment smoke checks against deployed PharmaAide services."""

import argparse
import json

from app.services.deployment_smoke import run_deployment_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--frontend-url")
    parser.add_argument("--timeout-seconds", type=float, default=10)
    args = parser.parse_args()

    report = run_deployment_smoke(
        backend_url=args.backend_url,
        frontend_url=args.frontend_url,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
