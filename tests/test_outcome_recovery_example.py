"""Exercise the reference application against IVal's actual public contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ival.campaigns import (
    CounterfactualBranchResult,
    CounterfactualEvaluation,
    compile_campaign_spec,
    compile_counterfactual_plan,
    load_counterfactual_plan,
    load_frozen_campaign_plan,
)
from examples.outcome_recovery import run

ROOT = Path(__file__).resolve().parents[1] / "examples" / "outcome_recovery"


def _plan():
    nominal = compile_campaign_spec(json.loads((ROOT / "campaign.json").read_text()))
    return compile_counterfactual_plan(nominal, run.load_interventions(ROOT / "interventions.json"))


def _branch_result(cell, *, success, **overrides):
    metadata = {
        "initial_state_sha256": "a" * 64,
        "fork_state_sha256": "b" * 64,
        "prefix_actions_sha256": "c" * 64,
        "checkpoint_sha256": "d" * 64,
        "simulator_revision": "frozen_libero_revision",
        "native_success_source": "native_environment_checker",
        "intervention_applied": cell.branch == "intervention",
        "intervention_id": cell.intervention.intervention_id,
    }
    metadata.update(overrides)
    return CounterfactualBranchResult(
        branch_attempt_id=cell.branch_attempt_id,
        pair_id=cell.pair_id,
        nominal_attempt_id=cell.nominal_attempt_id,
        branch=cell.branch,
        transition_index=cell.intervention.transition_index,
        intervention_id=cell.intervention.intervention_id,
        success=success,
        recovery_time_ms=None,
        failure_category=None,
        metadata=metadata,
    )


def test_example_builds_valid_existing_frozen_plans(tmp_path):
    output = tmp_path / "planned"
    assert run.main(["--plan-only", "--output", str(output)]) == 0
    nominal = load_frozen_campaign_plan(output / "campaign-plan.json")
    counterfactual = load_counterfactual_plan(output / "counterfactual-plan.json")
    assert len(nominal.attempts) == 2
    assert len(counterfactual.pairs) == 2
    provenance = json.loads((output / "provenance.json").read_text())
    assert provenance["native_outcomes_independently_verified"] is False
    assert provenance["mode"] == "plan_only"
    assert not (output / "counterfactual-results.jsonl").exists()


def test_example_loads_existing_frozen_plan_without_regenerating(tmp_path):
    original = tmp_path / "original"
    assert run.main(["--plan-only", "--output", str(original)]) == 0
    new = tmp_path / "new"
    assert run.main([
        "--plan-only", "--frozen-plan", str(original / "campaign-plan.json"),
        "--output", str(new),
    ]) == 0
    assert (new / "campaign-plan.json").read_bytes() == (
        original / "campaign-plan.json"
    ).read_bytes()


def test_example_refuses_overwrite(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "evidence.json").write_text("untouched")
    with pytest.raises(SystemExit) as exc:
        run.main(["--plan-only", "--output", str(output)])
    assert exc.value.code == 2
    assert (output / "evidence.json").read_text() == "untouched"


def test_example_rejects_multiple_interventions_to_avoid_nominal_pseudoreplication(tmp_path):
    data = json.loads((ROOT / "interventions.json").read_text())
    path = tmp_path / "multi.json"
    path.write_text(json.dumps(data + data))
    with pytest.raises(ValueError, match="exactly one"):
        run.load_interventions(path)


def test_complete_pair_agreement_is_contract_valid_not_native_verification():
    plan = _plan()
    results = tuple(
        _branch_result(cell, success=(cell.branch == "intervention"))
        for pair in plan.pairs
        for cell in (pair.nominal, pair.intervention)
    )
    report = run.assess_pairs(plan, results)
    assert report["contract_valid"] is True
    assert report["contract_complete_pairs"] == 2
    assert report["intervention_wins"] == 2
    assert "not_independently_verified" in report["scope"]


def test_missing_outcome_is_not_silently_counted_as_failure():
    plan = _plan()
    results = tuple(
        _branch_result(cell, success=None if cell.branch == "intervention" else True)
        for pair in plan.pairs
        for cell in (pair.nominal, pair.intervention)
    )
    report = run.assess_pairs(plan, results)
    assert report["contract_valid"] is False
    assert report["intervention_wins"] is None
    assert any("unknown_outcome" in issue for issue in report["issues"])


@pytest.mark.parametrize("changed", [
    {"initial_state_sha256": "e" * 64},
    {"fork_state_sha256": "e" * 64},
    {"prefix_actions_sha256": "e" * 64},
    {"checkpoint_sha256": "e" * 64},
    {"native_success_source": "another_scorer"},
    {"intervention_applied": False},
    {"intervention_id": "wrong_branch"},
])
def test_pair_parity_mismatch_fails_closed(changed):
    plan = _plan()
    results = [
        _branch_result(cell, success=True)
        for pair in plan.pairs
        for cell in (pair.nominal, pair.intervention)
    ]
    results[1] = replace(results[1], metadata={**results[1].metadata, **changed})
    report = run.assess_pairs(plan, results)
    assert report["contract_valid"] is False
    assert report["intervention_wins"] is None


def test_branch_identity_swap_rejected():
    plan = _plan()
    results = [
        _branch_result(cell, success=True)
        for pair in plan.pairs
        for cell in (pair.nominal, pair.intervention)
    ]
    results[1] = replace(results[1], branch_attempt_id="unplanned")
    assert run.assess_pairs(plan, results)["contract_valid"] is False


def test_external_evaluator_uses_existing_execution_and_reports_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(
        run, "load_evaluator",
        lambda _identifier: (
            lambda _cell, *, attempt, protocol: CounterfactualEvaluation(success=None),
            "f" * 64,
        ),
    )
    output = tmp_path / "unqualified"
    assert run.main(["--evaluator", "trusted_module:evaluate", "--output", str(output)]) == 2
    report = json.loads((output / "qualification.json").read_text())
    assert report["contract_valid"] is False
    assert len((output / "counterfactual-results.jsonl").read_text().splitlines()) == 4


def test_evaluator_receives_frozen_attempt_and_protocol():
    plan = compile_campaign_spec(json.loads((ROOT / "campaign.json").read_text()))
    counterfactual = compile_counterfactual_plan(
        plan, run.load_interventions(ROOT / "interventions.json")
    )
    seen = []

    def evaluator(cell, *, attempt, protocol):
        seen.append((attempt.key.attempt_id, attempt.task_seed, protocol["S"]["task"]["task_id"]))
        return CounterfactualEvaluation(success=None)

    bound = run.bind_evaluator(evaluator, plan)
    for pair in counterfactual.pairs:
        bound(pair.nominal)
        bound(pair.intervention)
    assert len(seen) == 4
    assert seen[0] == seen[1]
    assert seen[2] == seen[3]
    assert seen[0][0] != seen[2][0]
