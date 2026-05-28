"""Release-gate runner for PharmaAide evaluations.

The default gate is deterministic and offline. Live provider checks are added
only when explicitly requested so normal release checks do not spend tokens or
depend on external services.
"""

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationCommand:
    name: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationResult:
    name: str
    command: tuple[str, ...]
    return_code: int

    @property
    def ok(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True)
class EvaluationReport:
    results: tuple[EvaluationResult, ...]

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.results)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "results": [
                {
                    "name": result.name,
                    "ok": result.ok,
                    "return_code": result.return_code,
                    "command": list(result.command),
                }
                for result in self.results
            ],
        }


CommandRunner = Callable[[Sequence[str]], int]


def build_evaluation_commands(
    *,
    include_live_rag: bool = False,
    include_live_llm: bool = False,
) -> tuple[EvaluationCommand, ...]:
    """Build pytest commands for the selected release-gate scope."""
    commands = [
        EvaluationCommand(
            name="deterministic_evaluations",
            command=(
                sys.executable,
                "-m",
                "pytest",
                "tests/evaluations",
                "-m",
                "not live_embedding and not live_llm",
            ),
        )
    ]
    if include_live_rag:
        commands.append(
            EvaluationCommand(
                name="live_rag_evaluation",
                command=(
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/evaluations/test_live_rag_products_eval.py",
                    "-m",
                    "live_embedding",
                ),
            )
        )
    if include_live_llm:
        commands.append(
            EvaluationCommand(
                name="live_llm_smoke",
                command=(
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_analysis_graph.py",
                    "-m",
                    "live_llm",
                ),
            )
        )
    return tuple(commands)


def run_evaluation_release_gate(
    *,
    include_live_rag: bool = False,
    include_live_llm: bool = False,
    runner: CommandRunner | None = None,
) -> EvaluationReport:
    """Run selected evaluation commands and return a structured report."""
    effective_runner = runner or _run_command
    results = [
        EvaluationResult(
            name=command.name,
            command=command.command,
            return_code=effective_runner(command.command),
        )
        for command in build_evaluation_commands(
            include_live_rag=include_live_rag,
            include_live_llm=include_live_llm,
        )
    ]
    return EvaluationReport(results=tuple(results))


def _run_command(command: Sequence[str]) -> int:
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)
