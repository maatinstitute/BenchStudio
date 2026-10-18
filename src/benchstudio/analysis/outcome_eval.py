"""Frozen evaluation prompt roles for the outcome-conditioning arms."""

from __future__ import annotations

import math
from typing import Any, Iterable

_PROMPT_MODES = {
    "B": "task_only",
    "S": "task_only",
    "M": "task_only",
    "U": "all_metadata_unknown",
    "C": "desired_success",
    # Historical evaluator aliases remain ordinary task prompts.
    "base": "task_only",
    "control": "task_only",
    "corrective": "task_only",
}


def prompt_mode_for_arm(arm: str) -> str:
    try:
        return _PROMPT_MODES[arm]
    except KeyError as exc:
        raise ValueError(f"unknown evaluation arm: {arm}") from exc


def inference_kwargs(arm: str) -> dict[str, str]:
    return {"prompt_mode": prompt_mode_for_arm(arm)}


def boundary_outcome(native_success: bool) -> dict[str, object] | None:
    if native_success:
        return {"status": "excluded_prepolicy_success", "success": None, "steps": 0}
    return None


def first_attainment_step(successes: Iterable[bool]) -> int | None:
    """Return the one-based first native-success action, if any."""
    for index, success in enumerate(successes, start=1):
        if bool(success):
            return index
    return None


def validate_replay_attainment(expected_step: int | None, replay_step: int | None) -> None:
    if expected_step != replay_step:
        raise ValueError("independent replay changed the first attainment step")


def validate_evaluation_branch(
    branch: dict[str, Any] | None, prepared: dict[str, Any], max_penetration: float, label: str
) -> dict[str, Any]:
    """Accept one branch only after prespecified exclusions and replay checks."""
    intervention = prepared.get("intervention")
    if not isinstance(intervention, dict):
        raise ValueError(f"Missing intervention evidence: {label}")
    penetration = intervention.get("max_contact_penetration_m", 0.0)
    if (
        type(penetration) not in (int, float)
        or not math.isfinite(float(penetration))
        or penetration < 0
        or type(max_penetration) not in (int, float)
        or not math.isfinite(float(max_penetration))
        or max_penetration < 0
    ):
        raise ValueError(f"Invalid contact-screen threshold: {label}")
    supported = penetration <= max_penetration
    if prepared.get("supported") is not supported:
        raise ValueError(f"Contact screen mismatch: {label}")
    if not supported:
        if (
            not isinstance(branch, dict)
            or branch.get("status") != "excluded_by_prespecified_contact_screen"
            or branch.get("success") is not None
        ):
            raise ValueError(f"Invalid contact-screen exclusion: {label}")
        return {"success": None, "steps": 0, "excluded": True}
    if prepared.get("pre_policy_success"):
        if (
            not isinstance(branch, dict)
            or branch.get("status") != "excluded_prepolicy_success"
            or branch.get("success") is not None
        ):
            raise ValueError(f"Invalid pre-policy exclusion: {label}")
        return {"success": None, "steps": 0, "excluded": True}
    if (
        not isinstance(branch, dict)
        or branch.get("status") != "complete"
        or type(branch.get("success")) is not bool
        or type(branch.get("steps")) is not int
        or branch["steps"] < 0
    ):
        raise ValueError(f"Incomplete branch: {label}")
    replay = branch.get("independent_replay")
    if not isinstance(replay, dict):
        raise ValueError(f"Missing independent replay: {label}")
    attainment_step = branch.get("first_attainment_step")
    if branch["success"]:
        if (
            type(attainment_step) is not int
            or attainment_step < 1
            or attainment_step > branch["steps"]
        ):
            raise ValueError(f"Invalid first attainment step: {label}")
    elif attainment_step is not None:
        raise ValueError(f"Failed branch has an attainment step: {label}")
    error = replay.get("max_state_error")
    if (
        type(error) not in (int, float)
        or not math.isfinite(float(error))
        or error > 1e-8
        or replay.get("goal_matches") is not True
        or replay.get("observation_frames_checked") != branch["steps"] + 1
        or replay.get("first_attainment_step") != attainment_step
    ):
        raise ValueError(f"Replay audit failed: {label}")
    return {"success": branch["success"], "steps": branch["steps"], "excluded": False}
