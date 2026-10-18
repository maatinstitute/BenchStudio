from __future__ import annotations

import json

import pytest

from benchstudio.analysis import audit_counterfactual_outcomes, summarize_recovery_outcomes
from benchstudio.campaigns import (
    CampaignPlanner,
    CounterfactualEvaluation,
    Intervention,
    compile_counterfactual_plan,
    execute_counterfactual_plan,
)


def _plan():
    nominal = CampaignPlanner(
        run_id="robustness", scenario_id="task", conditions=[{"x": 1}], seeds=[7]
    ).freeze()
    return compile_counterfactual_plan(
        nominal, [Intervention("delay", 2, "sensor_delay", {"ms": 10})]
    )


def test_execute_counterfactual_plan_persists_paired_lineage(tmp_path):
    plan = _plan()
    output = tmp_path / "counterfactual"

    results = execute_counterfactual_plan(
        plan,
        lambda cell: CounterfactualEvaluation(
            success=cell.branch == "nominal",
            recovery_time_ms=120 if cell.branch == "intervention" else None,
            metadata={"branch": cell.branch},
        ),
        output=output,
    )

    assert [result.branch for result in results] == ["nominal", "intervention"]
    assert all(result.pair_id == plan.pairs[0].nominal.pair_id for result in results)
    records = [
        json.loads(line)
        for line in (output / "counterfactual-results.jsonl").read_text().splitlines()
    ]
    assert audit_counterfactual_outcomes(plan, records).complete
    recovery = summarize_recovery_outcomes(records)
    assert recovery.matched_pairs == 1
    assert recovery.recovery_rate == 0.0
    summary = json.loads((output / "counterfactual-summary.json").read_text())
    assert summary["unknown_outcome_count"] == 0


def test_execute_counterfactual_plan_preserves_unknown_outcomes(tmp_path):
    results = execute_counterfactual_plan(
        _plan(), lambda _: CounterfactualEvaluation(success=None), output=tmp_path
    )

    assert [result.success for result in results] == [None, None]
    summary = json.loads((tmp_path / "counterfactual-summary.json").read_text())
    assert summary["unknown_outcome_count"] == 2


def test_execute_counterfactual_plan_rejects_negative_recovery_time():
    with pytest.raises(ValueError, match="recovery_time_ms"):
        execute_counterfactual_plan(
            _plan(), lambda _: CounterfactualEvaluation(success=False, recovery_time_ms=-1)
        )
