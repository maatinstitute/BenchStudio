#!/usr/bin/env python3
"""Explain a contact-grasp rollout from its trace and frozen MuJoCo scene."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _trace_frames(path: Path) -> list[dict[str, Any]]:
    by_time: dict[int, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        t_ms = int(record.get("t_ms", 0))
        stream = str(record.get("stream", ""))
        state = record.get("state", {})
        frame = by_time.setdefault(t_ms, {"t_ms": t_ms})
        if stream == "robot_joints" and isinstance(state, dict):
            frame["joint_positions"] = state.get("joint_positions", {})
        elif stream == "objects" and isinstance(state, dict):
            frame["object_poses"] = state
        elif stream == "policy_action" and isinstance(state, dict):
            frame["joint_targets"] = state.get("joint_targets", {})
    return [
        frame
        for _, frame in sorted(by_time.items())
        if "joint_positions" in frame and "object_poses" in frame
    ]


def analyze(
    scenario_path: Path,
    manifest_path: Path,
    trace_path: Path,
    report_path: Path,
    contact_summary_path: Path | None = None,
) -> dict[str, Any]:
    import mujoco
    import numpy as np

    from backend.models.scenario import EpisodeManifest
    from backend.scripts.scenario_episode_worker import _build_backend
    from backend.services.scenario_loader import load_scenario
    from backend.services.sim_backends.types import ObjectPose, SimState

    scenario = load_scenario(scenario_path)
    manifest = EpisodeManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    report = _load_json(report_path)
    contact_summary = (
        _load_json(contact_summary_path)
        if contact_summary_path is not None and contact_summary_path.is_file()
        else {}
    )
    frames = _trace_frames(trace_path)
    if not frames:
        raise ValueError(f"no replayable state frames in {trace_path}")

    backend = _build_backend("mujoco", scenario, str(scenario_path))
    backend.load_scene(physics_timestep_s=scenario.runtime.physics_timestep_s)
    backend.reset_episode(manifest)

    close_time_ms = None
    policy_file = scenario_path.parent / str(
        scenario.policy.params.get("waypoints_file", "waypoints.json")
    )
    if policy_file.is_file():
        policy = _load_json(policy_file)
        for waypoint in policy.get("waypoints", []):
            if isinstance(waypoint, dict) and "close" in str(waypoint.get("label", "")).lower():
                close_time_ms = round(float(waypoint.get("time_s", 0.0)) * 1000)
                break

    contacts: list[dict[str, Any]] = []
    initial_position = None
    final_position = None
    max_height = float("-inf")
    minimum_contact_distance = None
    bilateral_frames = 0
    contact_frames = 0
    max_contact_count = 0
    contact_geom_names: set[str] = set()
    final_gripper_position = None
    final_gripper_target = None
    previous_position = None
    largest_frame_displacement = 0.0
    largest_frame_displacement_ms = None

    for frame in frames:
        objects = frame["object_poses"]
        joints = frame["joint_positions"]
        cube = objects.get("grasp_cube", {}) if isinstance(objects, dict) else {}
        cube_position = cube.get("position_xyz", []) if isinstance(cube, dict) else []
        cube_quat = cube.get("quat_wxyz", []) if isinstance(cube, dict) else []
        if len(cube_position) != 3 or len(cube_quat) != 4:
            continue
        position = tuple(float(value) for value in cube_position)
        if previous_position is not None:
            frame_displacement = float(
                np.linalg.norm(np.array(position) - np.array(previous_position))
            )
            if frame_displacement > largest_frame_displacement:
                largest_frame_displacement = frame_displacement
                largest_frame_displacement_ms = frame["t_ms"]
        previous_position = position
        if initial_position is None:
            initial_position = position
        final_position = position
        max_height = max(max_height, position[2])
        if isinstance(joints, dict) and "gripper" in joints:
            final_gripper_position = float(joints["gripper"])
        targets = frame.get("joint_targets", {})
        if isinstance(targets, dict) and "gripper" in targets:
            final_gripper_target = float(targets["gripper"])
        backend.set_state(
            SimState(
                sim_time_s=frame["t_ms"] / 1000.0,
                joint_positions={str(k): float(v) for k, v in joints.items()},
                joint_velocities={},
                object_poses={
                    "grasp_cube": ObjectPose(
                        position_xyz=position,
                        quat_wxyz=tuple(float(value) for value in cube_quat),
                    )
                },
            )
        )
        frame_geoms: set[str] = set()
        frame_distances: list[float] = []
        frame_count = 0
        for index in range(backend._data.ncon):
            contact = backend._data.contact[index]
            pair = []
            for geom_id in (int(contact.geom1), int(contact.geom2)):
                name = mujoco.mj_id2name(
                    backend._model, mujoco.mjtObj.mjOBJ_GEOM, geom_id
                ) or f"geom_{geom_id}"
                pair.append(name)
            if not any(name.endswith("grasp_cube") for name in pair) or not any(
                name.startswith("robot/") for name in pair
            ):
                continue
            frame_count += 1
            frame_distances.append(float(contact.dist))
            frame_geoms.update(name for name in pair if name.startswith("robot/"))
        if frame_count:
            contact_frames += 1
            max_contact_count = max(max_contact_count, frame_count)
            contact_geom_names.update(frame_geoms)
            frame_min = min(frame_distances)
            minimum_contact_distance = (
                frame_min
                if minimum_contact_distance is None
                else min(minimum_contact_distance, frame_min)
            )
            bilateral = {
                "robot/fixed_finger_contact_mesh",
                "robot/moving_finger_contact_mesh",
            }.issubset(frame_geoms)
            bilateral_frames += int(bilateral)
            contacts.append(
                {
                    "t_ms": frame["t_ms"],
                    "contact_count": frame_count,
                    "robot_geoms": sorted(frame_geoms),
                    "minimum_distance_m": frame_min,
                    "bilateral": bilateral,
                    "cube_position_xyz": list(position),
                }
            )

    if initial_position is None or final_position is None:
        raise ValueError("trace does not contain a grasp_cube pose")
    horizontal_displacement = float(
        np.linalg.norm(np.array(final_position[:2]) - np.array(initial_position[:2]))
    )
    max_lift = max(0.0, max_height - initial_position[2])
    telemetry_capture = contact_summary.get("capture", {})
    telemetry_contact = contact_summary.get("contact", {})
    telemetry_equivalence = contact_summary.get("equivalence", {})
    telemetry_available = (
        isinstance(telemetry_capture, dict)
        and isinstance(telemetry_contact, dict)
        and isinstance(telemetry_equivalence, dict)
        and telemetry_equivalence.get("verified") is True
    )
    first_contact_ms = contacts[0]["t_ms"] if contacts else None
    if telemetry_available and telemetry_contact.get("first_contact_s") is not None:
        first_contact_ms = round(float(telemetry_contact["first_contact_s"]) * 1000)
        contact_frames = int(telemetry_capture.get("contact_physics_steps", 0) or 0)
        bilateral_frames = int(
            telemetry_capture.get("bilateral_contact_physics_steps", 0) or 0
        )
        contact_geom_names.update(telemetry_contact.get("robot_contact_geoms", []))
    first_contact_before_close = bool(
        first_contact_ms is not None
        and close_time_ms is not None
        and first_contact_ms < close_time_ms
    )

    if report.get("success") is True:
        failure_class = None
        explanation = "The contact-grasp episode satisfied the frozen success checks."
    elif first_contact_ms is None and largest_frame_displacement > 0.02:
        failure_class = "transient_impact_ejected_object"
        explanation = (
            "The cube was abruptly displaced between retained control states. "
            "No high-rate contact telemetry was available to resolve the impact; "
            "bilateral retention never formed."
        )
    elif first_contact_ms is None:
        failure_class = "no_robot_object_contact"
        explanation = "The gripper never made recorded contact with the cube."
    elif first_contact_before_close and bilateral_frames == 0:
        failure_class = "approach_collision_ejected_object"
        explanation = (
            "Physics-step telemetry records gripper contact before the close phase. "
            "The jaws never formed bilateral retention and displaced the cube instead."
        )
    elif bilateral_frames == 0:
        failure_class = "unilateral_contact_no_grip"
        explanation = "Robot contact occurred, but both finger pads never contacted the cube together."
    elif max_lift < 0.10:
        failure_class = "bilateral_contact_insufficient_lift"
        explanation = "Both finger pads contacted the cube, but the lift threshold was not reached."
    else:
        failure_class = "retention_or_stability_failure"
        explanation = "The cube lifted but did not satisfy the retained stability requirement."

    return {
        "schema": "benchstudio.contact_grasp_analysis.v1",
        "episode_index": manifest.episode_index,
        "seed": manifest.seed,
        "backend": "mujoco",
        "success": report.get("success") is True,
        "stop_reason": report.get("stop_reason"),
        "failure_class": failure_class,
        "explanation": explanation,
        "contact_model": {
            "mode": "physics_contact",
            "grasp_attach_used": report.get("grasp_attach_used") is True,
            "fixed_finger_geom": "robot/fixed_finger_contact_mesh",
            "moving_finger_geom": "robot/moving_finger_contact_mesh",
        },
        "timeline": {
            "close_command_ms": close_time_ms,
            "first_contact_ms": first_contact_ms,
            "last_contact_ms": contacts[-1]["t_ms"] if contacts else None,
            "first_contact_before_close": first_contact_before_close,
            "contact_frames": contact_frames,
            "bilateral_contact_frames": bilateral_frames,
            "max_simultaneous_contacts": max_contact_count,
        },
        "motion": {
            "initial_cube_position_xyz": list(initial_position),
            "final_cube_position_xyz": list(final_position),
            "horizontal_displacement_m": horizontal_displacement,
            "max_lift_m": max_lift,
            "largest_frame_displacement_m": largest_frame_displacement,
            "largest_frame_displacement_t_ms": largest_frame_displacement_ms,
        },
        "gripper": {
            "final_position_rad": final_gripper_position,
            "final_target_rad": final_gripper_target,
            "final_tracking_error_rad": (
                abs(final_gripper_position - final_gripper_target)
                if final_gripper_position is not None and final_gripper_target is not None
                else None
            ),
            "contact_geoms_observed": sorted(contact_geom_names),
            "minimum_contact_distance_m": minimum_contact_distance,
        },
        "physics_contact_telemetry": contact_summary if telemetry_available else None,
        "contact_checkpoints": contacts[:3] + contacts[-3:] if len(contacts) > 6 else contacts,
        "limitations": (
            [
                "Contact forces and impulses are MuJoCo solver outputs from a deterministic diagnostic replay, not calibrated hardware measurements.",
                "The diagnostic replay is accepted only when outcome, stop reason, step count, and final cube position match the evaluated run.",
            ]
            if telemetry_available
            else [
                "Contact reconstruction uses 50 Hz retained state snapshots; impacts shorter than 20 ms may occur between frames.",
                "No contact force is claimed because the retained trace does not include solver impulses.",
            ]
        ),
        "source_digests": {
            "scenario_sha256": _digest(scenario_path),
            "manifest_sha256": _digest(manifest_path),
            "trace_sha256": _digest(trace_path),
            "report_sha256": _digest(report_path),
            "policy_sha256": _digest(policy_file) if policy_file.is_file() else None,
            "contact_telemetry_summary_sha256": (
                _digest(contact_summary_path)
                if contact_summary_path is not None and contact_summary_path.is_file()
                else None
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--contact-summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = analyze(
        args.scenario,
        args.manifest,
        args.trace,
        args.report,
        args.contact_summary,
    )
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"contact_analysis={args.output} "
        f"failure_class={payload['failure_class']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
