"""RoboPAD restored-pose OSC initialization invariants."""

from __future__ import annotations

from typing import Any

VERSION = "restored_pose_goals_v1"


class InitializationFailure(ValueError):
    def __init__(self, error: Exception, record: dict[str, Any]):
        super().__init__(str(error))
        self.record = record


def snapshot(controller: Any, gripper: Any) -> dict[str, Any]:
    import numpy as np

    def value(name: str):
        item = getattr(controller, name)
        if item is None:
            return None
        array = np.asarray(item)
        if array.dtype.kind not in "biuf" or not np.isfinite(array).all():
            raise ValueError("invalid OSC snapshot " + name)
        return array.tolist()

    return {
        "osc": {
            name: value(name)
            for name in ("goal_pos", "goal_ori", "ee_pos", "ee_ori_mat", "new_update")
        },
        "gripper": {
            "class_name": type(gripper).__name__,
            "dof": gripper.dof,
            "speed": float(gripper.speed),
            "current_action": np.asarray(gripper.current_action).tolist(),
        },
    }


def initialize_restored_pose(env: Any, *, version: str) -> dict[str, Any]:
    import numpy as np

    record: dict[str, Any] = {
        "version": version,
        "status": "started",
        "controller_update_attempted": False,
        "controller_reset_attempted": False,
    }
    try:
        if version != VERSION:
            raise ValueError("unreviewed initialization version")
        if len(env.env.robots) != 1:
            raise ValueError("one robot required")
        robot = env.env.robots[0]
        controller, gripper = robot.controller, robot.gripper
        state = np.asarray(env.get_sim_state()).copy()
        record["before"] = snapshot(controller, gripper)
        if (
            type(gripper).__name__ != "PandaGripper"
            or gripper.dof != 1
            or float(gripper.speed) != 0.01
            or not np.array_equal(np.asarray(gripper.current_action), np.array([0.0]))
        ):
            raise ValueError("unexpected fresh reference-matched gripper initialization")
        record["controller_update_attempted"] = True
        controller.update(force=True)
        record["controller_reset_attempted"] = True
        controller.reset_goal()
        record["after"] = snapshot(controller, gripper)
        site = env.sim.model.site_name2id(controller.eef_name)
        if site < 0:
            raise ValueError("missing end effector site")
        actual_pos = np.asarray(env.sim.data.site_xpos[site])
        actual_rotation = np.asarray(env.sim.data.site_xmat[site]).reshape(3, 3)
        record["refreshed_cache_matches_site"] = bool(
            np.array_equal(controller.ee_pos, actual_pos)
            and np.array_equal(controller.ee_ori_mat, actual_rotation)
        )
        record["state_unchanged"] = bool(np.array_equal(state, env.get_sim_state()))
        record["goal_matches_refreshed_pose"] = bool(
            np.array_equal(controller.goal_pos, controller.ee_pos)
            and np.array_equal(controller.goal_ori, controller.ee_ori_mat)
        )
        record["gripper_unchanged"] = record["before"]["gripper"] == record["after"]["gripper"]
        if not all(
            record[key]
            for key in (
                "refreshed_cache_matches_site",
                "state_unchanged",
                "goal_matches_refreshed_pose",
                "gripper_unchanged",
            )
        ):
            raise ValueError("restored initialization invariant failed")
        record["status"] = "invariants_passed_not_scientific_validation"
        return record
    except Exception as exc:
        record.update(status="failed", error=repr(exc))
        raise InitializationFailure(exc, record) from exc
