import itertools

import pytest

from benchstudio.analysis.missingness import robopad_paired_bounds
from benchstudio.analysis.robopad_exposure import audit_splits, demo_family


def test_paired_bounds_match_all_possible_completions():
    plan = {"a": 0.2, "b": 0.3, "c": 0.5}
    result = robopad_paired_bounds(plan, {"a": (1, None), "b": (None, 0)})
    possible = [
        0.2 * (1 - original_a) + 0.3 * learner_b + 0.5 * (learner_c - original_c)
        for original_a, learner_b, learner_c, original_c in itertools.product((0, 1), repeat=4)
    ]
    assert result["lower"] == min(possible)
    assert result["upper"] == max(possible)
    assert result["missing_arm_count"] == 4
    assert result["point_estimate"] is None


def test_paired_bounds_preserve_denominator_and_reject_invalid_plans():
    result = robopad_paired_bounds({"a": 0.5, "b": 0.5}, {"a": (1, 1)})
    assert (result["lower"], result["upper"]) == (-0.5, 0.5)
    assert (
        robopad_paired_bounds({"a": 0.25, "b": 0.75}, {"a": (1, 0), "b": (0, 1)})["point_estimate"]
        == -0.5
    )
    for plan, outcomes in [
        ({}, {}),
        ({"a": 0.5}, {}),
        ({"a": 1.0}, {"b": (1, 0)}),
        ({"a": 1.0}, {"a": (0.5, 0)}),
        ({"a": float("nan")}, {}),
    ]:
        with pytest.raises(ValueError):
            robopad_paired_bounds(plan, outcomes)


def _inventory():
    return {"schema_version": 1, "families": [{"family_id": "libero_object/task0/demo1"}]}


def test_exposure_audit_is_fail_closed_and_keeps_descendants_together():
    result = audit_splits(
        _inventory(), [{"family_id": "libero_object/task0/demo1", "split": "protocol_validation"}]
    )
    assert result["quarantined_families"] == ["libero_object/task0/demo1"]
    assert result["freshness_certified"] is False
    result = audit_splits(
        _inventory(),
        [
            {"family_id": "libero_object/task0/demo42", "split": split}
            for split in ("development", "final_test")
        ],
    )
    assert result["cross_split_families"] == ["libero_object/task0/demo42"]
    assert result["structurally_disjoint"] is False
    result = audit_splits(
        _inventory(), [{"family_id": "libero_spatial/task0/initial1", "split": "final_test"}]
    )
    assert result["structurally_disjoint"] is True
    assert result["freshness_certified"] is False


def test_exposure_identity_and_split_validation():
    assert demo_family({"task_id": 2, "demo_index": 38}) == "libero_object/task2/demo38"
    for row in [
        {"split": "final_test"},
        {"family_id": "task0/demo1", "split": "final_test"},
        {"family_id": "libero_object/task0/demo1/seed2", "split": "final_test"},
    ]:
        with pytest.raises(ValueError):
            audit_splits(_inventory(), [row])
    for rows in ([], [{"family_id": "libero_object/task0/demo42", "split": "test"}]):
        with pytest.raises(ValueError):
            audit_splits(_inventory(), rows)
