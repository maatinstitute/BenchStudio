from __future__ import annotations

import pytest

import json

from reva.campaigns import build_outcome_plan, load_outcome_plan


def populations():
    return [f"recovery-{index}" for index in range(24)], [f"reset-{index}" for index in range(24)]


def test_preflight_enumerates_the_frozen_science_matrix():
    recovery, reset = populations()
    plan = build_outcome_plan(recovery_parents=recovery, reset_parents=reset)
    assert plan["status"] == "preflight_only"
    assert plan["counts"]["training_checkpoints"] == 20
    assert plan["counts"]["recovery_continuations"] == 1512
    assert plan["counts"]["reset_continuations"] == 504
    assert plan["counts"]["reserved_continuations"] == 2016
    assert plan["counts"]["max_policy_queries"] == 567120
    assert len(plan["training_cells"]) == 20


def test_policy_and_training_ids_are_unique_and_explicit():
    recovery, reset = populations()
    plan = build_outcome_plan(recovery_parents=recovery, reset_parents=reset)
    training_ids = {row["cell_id"] for row in plan["training_cells"]}
    assert len(training_ids) == 20
    assert {row["arm"] for row in plan["training_cells"]} == {"S", "M", "U", "C"}
    assert {row["seed"] for row in plan["training_cells"]} == {123, 456, 789, 1011, 1213}
    assert all(
        row["policy_id"] != row["parent_id"] for row in plan["recovery_cells"] + plan["reset_cells"]
    )


def test_duplicate_wrong_population_and_overlap_fail_closed():
    recovery, reset = populations()
    with pytest.raises(ValueError, match="unique"):
        build_outcome_plan(recovery_parents=recovery + [recovery[0]], reset_parents=reset)
    with pytest.raises(ValueError, match="24"):
        build_outcome_plan(recovery_parents=recovery[:23], reset_parents=reset)
    with pytest.raises(ValueError, match="path-safe"):
        build_outcome_plan(recovery_parents=recovery[:-1] + ["../foreign"], reset_parents=reset)
    with pytest.raises(ValueError, match="disjoint"):
        build_outcome_plan(recovery_parents=recovery, reset_parents=[*reset[:-1], recovery[0]])


def test_outcome_plan_loader_binds_file_and_rechecks_counts(tmp_path):
    recovery, reset = populations()
    path = tmp_path / "outcome-plan.json"
    path.write_text(
        json.dumps(build_outcome_plan(recovery_parents=recovery, reset_parents=reset)),
        encoding="utf-8",
    )
    plan, file_sha256 = load_outcome_plan(path)
    assert plan["status"] == "preflight_only"
    assert plan["counts"]["max_policy_queries"] == 567120
    assert len(file_sha256) == 64


def test_outcome_plan_loader_rejects_tampered_payload(tmp_path):
    recovery, reset = populations()
    payload = build_outcome_plan(recovery_parents=recovery, reset_parents=reset)
    payload["counts"]["max_policy_queries"] += 1
    path = tmp_path / "tampered-outcome-plan.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        load_outcome_plan(path)
