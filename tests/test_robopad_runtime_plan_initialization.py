from types import SimpleNamespace as NS

import numpy as np
import pytest

from reva.campaigns.robopad_runtime_plan import child_runs, validate_plan
from reva.integrations.robopad_initialization import (
    VERSION,
    InitializationFailure,
    initialize_restored_pose,
)


class PandaGripper:
    dof = 1
    speed = 0.01

    def __init__(self):
        self.current_action = np.array([0.0])


def _environment():
    calls = []
    state = np.array([0.0, 1.0, 2.0])
    actual = np.array([0.1, 0.2, 0.3])
    controller = NS(
        goal_pos=np.ones(3),
        goal_ori=np.eye(3) * 2,
        ee_pos=np.ones(3) * 5,
        ee_ori_mat=np.eye(3),
        new_update=False,
        eef_name="eef",
    )

    def update(force=False):
        calls.append(("update", force))
        controller.ee_pos = actual.copy()
        controller.ee_ori_mat = np.eye(3)
        controller.new_update = False

    def reset():
        calls.append(("reset",))
        controller.goal_pos = controller.ee_pos.copy()
        controller.goal_ori = controller.ee_ori_mat.copy()

    controller.update = update
    controller.reset_goal = reset
    env = NS(
        env=NS(robots=[NS(controller=controller, gripper=PandaGripper())]),
        get_sim_state=lambda: state.copy(),
        sim=NS(
            model=NS(site_name2id=lambda _: 0),
            data=NS(site_xpos=np.array([actual]), site_xmat=np.eye(3)[None]),
        ),
    )
    return env, controller, state, calls


def test_runtime_plan_has_fixed_replays_and_rejects_mutation():
    runs = child_runs(0, 0)
    assert len(runs) == 54
    assert sum(row["kind"] == "replay" for row in runs) == 1
    assert all(
        row["original"] in [item["id"] for item in runs[:index]]
        for index, row in enumerate(runs)
        if row["kind"] == "replay"
    )
    with pytest.raises(ValueError):
        child_runs(True, 0)


def test_restored_initialization_refreshes_goal_without_mutating_state():
    env, controller, state, calls = _environment()
    record = initialize_restored_pose(env, version=VERSION)
    assert calls == [("update", True), ("reset",)]
    np.testing.assert_array_equal(state, [0.0, 1.0, 2.0])
    assert record["refreshed_cache_matches_site"]
    assert record["goal_matches_refreshed_pose"]
    assert record["before"]["osc"]["goal_pos"] != record["after"]["osc"]["goal_pos"]


def test_unexpected_gripper_fails_before_controller_mutation():
    env, _, _, calls = _environment()
    env.env.robots[0].gripper.current_action = np.array([1.0])
    with pytest.raises(InitializationFailure) as caught:
        initialize_restored_pose(env, version=VERSION)
    assert caught.value.record["controller_update_attempted"] is False
    assert calls == []


def test_runtime_plan_requires_explicit_version_and_frozen_limits():
    runs = child_runs(0, 0)
    config = {
        "initialization_version": VERSION,
        "task": 0,
        "demo": 0,
        "runs": runs,
        "allocation_sha256": "48fd05bbee3caf771cae05be2070ec13d4f43df9510902be1f83c0a6700c36a9",
        "allocation_manifest": {
            "sha256": "48fd05bbee3caf771cae05be2070ec13d4f43df9510902be1f83c0a6700c36a9"
        },
        "allocation": [],
        "cell_runtime_reserve_seconds": 120,
        "limits": {
            "application_seconds": 3300,
            "total_bytes": 4_000_000_000,
            "cache_bytes": 20_000_000,
            "cell_bytes": 70_000_000,
            "accounting_bytes": 1_000_000,
            "max_actions": 10800,
            "max_suffix_queries": 1080,
            "max_cache_queries": 2,
        },
    }
    with pytest.raises(ValueError):
        validate_plan(config)
    config["allocation"] = [
        list(slot)
        for slot in __import__(
            "reva.campaigns.robopad_assay_plan", fromlist=["remaining_slots"]
        ).remaining_slots()
    ]
    assert len(validate_plan(config)) == 54
