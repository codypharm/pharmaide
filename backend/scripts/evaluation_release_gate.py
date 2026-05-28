"""Run PharmaAide release-gate evaluations."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.evaluation_release_gate import run_evaluation_release_gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-live-rag",
        action="store_true",
        help="Also run the live RAG eval. Requires PHARMAIDE_RUN_LIVE_RAG_EVAL=1.",
    )
    parser.add_argument(
        "--include-live-llm",
        action="store_true",
        help="Also run the live LLM smoke test. Requires PHARMAIDE_RUN_LIVE_LLM=1.",
    )
    args = parser.parse_args()

    report = run_evaluation_release_gate(
        include_live_rag=args.include_live_rag,
        include_live_llm=args.include_live_llm,
    )
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
