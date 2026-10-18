from __future__ import annotations

import pytest

from benchstudio.campaigns import (
    PerturbationDimension,
    compile_search_plan,
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
