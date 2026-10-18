from __future__ import annotations

import pytest

from benchstudio.campaigns import (
    PerturbationDimension,
    SearchEvaluation,
    audit_search_results,
    build_search_candidates,
    compile_search_plan,
    execute_search_plan,
    load_search_plan,
    minimize_counterexample,
    validate_search_plan,
)


def test_search_plan_is_deterministic_and_bounded():
    dimensions = (
        PerturbationDimension("object_x", (-1.0, 0.0, 1.0)),
        PerturbationDimension("delay_ms", (0, 20)),
    )
    first = compile_search_plan(
        run_id="search",
        scenario_id="pick",
        base_condition_id="base",
        dimensions=dimensions,
        seeds=[1, 2],
        max_cases=4,
    )
    second = compile_search_plan(
        run_id="search",
        scenario_id="pick",
        base_condition_id="base",
        dimensions=dimensions,
        seeds=[1, 2],
        max_cases=4,
    )
    assert first == second
    assert len(first.cases) == 4
    assert len({case.case_id for case in first.cases}) == 4


def test_counterexample_minimizer_preserves_failure():
    result = minimize_counterexample(
        {"object_x": 1.0, "delay_ms": 20},
        lambda values: values["object_x"] >= 0.5 and values["delay_ms"] >= 10,
        candidate_values={"object_x": (0.0, 0.5, 1.0), "delay_ms": (0, 10, 20)},
    )
    assert result.failure_preserved
    assert result.parameters == {"object_x": 0.5, "delay_ms": 10}
    assert result.tested_candidates > 1


def test_search_plan_rejects_duplicate_dimension_names():
    with pytest.raises(ValueError, match="dimension names"):
        compile_search_plan(
            run_id="run",
            scenario_id="task",
            base_condition_id="base",
            dimensions=(
                PerturbationDimension("x", (1,)),
                PerturbationDimension("x", (2,)),
            ),
            seeds=[1],
        )


def test_search_plan_can_be_written_and_validated_before_confirmation(tmp_path):
    plan = compile_search_plan(
        run_id="search",
        scenario_id="task",
        base_condition_id="base",
        dimensions=(PerturbationDimension("x", (0, 1)),),
        seeds=[1],
    )
    path = tmp_path / "search-plan.json"
    plan.write(path)
    assert path.is_file()
    assert validate_search_plan(plan) == []
    tampered = type(plan)(plan.run_id, plan.scenario_id, plan.cases[:-1], plan.plan_digest_sha256)
    assert "plan_digest_sha256 does not match cases" in validate_search_plan(tampered)


def test_search_plan_round_trips_through_independent_loader(tmp_path):
    plan = compile_search_plan(
        run_id="search",
        scenario_id="task",
        base_condition_id="base",
        dimensions=(PerturbationDimension("x", (0, 1)),),
        seeds=[1],
    )
    path = tmp_path / "search-plan.json"
    plan.write(path)
    assert load_search_plan(path) == plan


def test_search_plan_loader_rejects_digest_tampering(tmp_path):
    plan = compile_search_plan(
        run_id="search",
        scenario_id="task",
        base_condition_id="base",
        dimensions=(PerturbationDimension("x", (0, 1)),),
        seeds=[1],
    )
    path = tmp_path / "search-plan.json"
    plan.write(path)
    payload = __import__("json").loads(path.read_text())
    payload["cases"][0]["parameters"]["x"] = 99
    path.write_text(__import__("json").dumps(payload))
    with pytest.raises(ValueError, match="digest"):
        load_search_plan(path)


def test_search_execution_persists_failures_as_confirmation_candidates(tmp_path):
    plan = compile_search_plan(
        run_id="search-run",
        scenario_id="task",
        base_condition_id="base",
        dimensions=(PerturbationDimension("delay_ms", (0, 20)),),
        seeds=[1, 2],
    )

    results = execute_search_plan(
        plan,
        lambda case: SearchEvaluation(
            failed=case.parameters["delay_ms"] == 20,
            metadata={"observed_steps": case.seed},
        ),
        output=tmp_path / "search-evidence",
    )
    assert len(results) == 4
    assert sum(result.failed for result in results) == 2
    assert all(result.failure_digest_sha256 is not None for result in results if result.failed)
    candidates = build_search_candidates(plan, results)
    assert len(candidates) == 2
    assert {candidate.source_seed for candidate in candidates} == {1, 2}
    summary = __import__("json").loads(
        (tmp_path / "search-evidence" / "search-summary.json").read_text()
    )
    assert summary["scheduled_case_count"] == 4
    assert summary["failed_case_count"] == 2
    rows = [
        __import__("json").loads(line)
        for line in (tmp_path / "search-evidence" / "search-results.jsonl").read_text().splitlines()
    ]
    assert audit_search_results(plan, rows).complete


def test_search_result_audit_rejects_tampered_case_lineage():
    plan = compile_search_plan(
        run_id="search-run",
        scenario_id="task",
        base_condition_id="base",
        dimensions=(PerturbationDimension("x", (0,)),),
        seeds=[1],
    )
    result = {
        "case_id": plan.cases[0].case_id,
        "scenario_id": plan.cases[0].scenario_id,
        "base_condition_id": plan.cases[0].base_condition_id,
        "seed": 999,
        "parameters": dict(plan.cases[0].parameters),
        "failed": False,
    }
    audit = audit_search_results(plan, [result])
    assert audit.complete is False
    assert any("seed does not match frozen plan" in issue for issue in audit.lineage_issues)


def test_search_result_audit_rejects_invalid_failure_evidence():
    plan = compile_search_plan(
        run_id="search-run",
        scenario_id="task",
        base_condition_id="base",
        dimensions=(PerturbationDimension("x", (0,)),),
        seeds=[1],
    )
    case = plan.cases[0]
    audit = audit_search_results(
        plan,
        [
            {
                "case_id": case.case_id,
                "scenario_id": case.scenario_id,
                "base_condition_id": case.base_condition_id,
                "seed": case.seed,
                "parameters": dict(case.parameters),
                "failed": True,
                "failure_digest_sha256": "not-a-digest",
            }
        ],
    )
    assert audit.complete is False
    assert any("lowercase SHA-256" in issue for issue in audit.lineage_issues)


def test_search_execution_rejects_failure_digest_on_success():
    plan = compile_search_plan(
        run_id="search-run",
        scenario_id="task",
        base_condition_id="base",
        dimensions=(PerturbationDimension("x", (0,)),),
        seeds=[1],
    )
    with pytest.raises(ValueError, match="successful case"):
        execute_search_plan(
            plan,
            lambda _: SearchEvaluation(False, "a" * 64),
        )
