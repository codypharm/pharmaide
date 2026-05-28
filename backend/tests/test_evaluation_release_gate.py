"""Release-gate evaluation runner behavior."""

from app.services.evaluation_release_gate import (
    build_evaluation_commands,
    run_evaluation_release_gate,
)


def test_release_gate_defaults_to_deterministic_evaluations_only() -> None:
    commands = build_evaluation_commands()

    assert [command.name for command in commands] == ["deterministic_evaluations"]
    assert commands[0].command[-3:] == (
        "tests/evaluations",
        "-m",
        "not live_embedding and not live_llm",
    )


def test_release_gate_adds_live_commands_only_when_requested() -> None:
    commands = build_evaluation_commands(include_live_rag=True, include_live_llm=True)

    assert [command.name for command in commands] == [
        "deterministic_evaluations",
        "live_rag_evaluation",
        "live_llm_smoke",
    ]
    assert commands[1].command[-3:] == (
        "tests/evaluations/test_live_rag_products_eval.py",
        "-m",
        "live_embedding",
    )
    assert commands[2].command[-3:] == ("tests/test_analysis_graph.py", "-m", "live_llm")


def test_release_gate_reports_failures_without_stopping_early() -> None:
    calls: list[tuple[str, ...]] = []

    def fake_runner(command: tuple[str, ...]) -> int:
        calls.append(command)
        return 1 if any("test_live_rag_products_eval.py" in part for part in command) else 0

    report = run_evaluation_release_gate(include_live_rag=True, runner=fake_runner)

    assert report.ok is False
    assert [result.ok for result in report.results] == [True, False]
    assert len(calls) == 2
    assert report.as_dict()["ok"] is False
