#!/usr/bin/env python3
"""Run a deterministic MuJoCo diagnostic replay with physics-step contact telemetry."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(values: list[float]) -> bool:
    return all(math.isfinite(value) for value in values)


def record(
    scenario_path: Path,
    manifest_path: Path,
    reference_report_path: Path,
    output_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    import mujoco
    import numpy as np

    from backend.models.scenario import EpisodeManifest
    from backend.scripts.scenario_episode_worker import _build_backend
    from backend.services.scenario_loader import load_scenario
    from backend.services.scenario_policies import build_scenario_policy
    from backend.services.scenario_runtime.episode_runner import run_episode

    scenario = load_scenario(scenario_path)
    manifest = EpisodeManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    reference_report = _load_json(reference_report_path)
    backend = _build_backend("mujoco", scenario, str(scenario_path))
    policy = build_scenario_policy(scenario, str(scenario_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle = output_path.open("wb")
    digest = hashlib.sha256()
    record_count = 0
    physics_steps = 0
    contact_physics_steps = 0
    bilateral_physics_steps = 0
    first_contact_s = None
    last_contact_s = None
    peak_normal_force_n = 0.0
    peak_tangential_force_n = 0.0
    peak_penetration_m = 0.0
    normal_impulse_ns = 0.0
    tangential_impulse_ns = 0.0
    contact_geom_names: set[str] = set()
    current_targets: dict[str, float] = {}
    control_step = 0
    original_step = backend.step

    def write_record(payload: dict[str, Any]) -> None:
        nonlocal record_count
        line = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
        handle.write(line)
        digest.update(line)
        record_count += 1

    def joint_state() -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        positions: dict[str, float] = {}
        velocities: dict[str, float] = {}
        actuator_forces: dict[str, float] = {}
        for actuator_index, prefixed_name in enumerate(backend._actuated_joint_names):
            joint_id = mujoco.mj_name2id(
                backend._model, mujoco.mjtObj.mjOBJ_JOINT, prefixed_name
            )
            bare_name = prefixed_name.removeprefix("robot/")
            positions[bare_name] = float(
                backend._data.qpos[backend._model.jnt_qposadr[joint_id]]
            )
            velocities[bare_name] = float(
                backend._data.qvel[backend._model.jnt_dofadr[joint_id]]
            )
            if actuator_index < len(backend._data.actuator_force):
                actuator_forces[bare_name] = float(
                    backend._data.actuator_force[actuator_index]
                )
        return positions, velocities, actuator_forces

    def instrumented_step(joint_targets: dict[str, float] | None, substeps: int) -> None:
        nonlocal physics_steps, contact_physics_steps, bilateral_physics_steps
        nonlocal first_contact_s, last_contact_s, peak_normal_force_n
        nonlocal peak_tangential_force_n, peak_penetration_m
        nonlocal normal_impulse_ns, tangential_impulse_ns, current_targets, control_step
        control_step += 1
        if joint_targets:
            current_targets = {str(key): float(value) for key, value in joint_targets.items()}
            for joint_name, target in joint_targets.items():
                backend._set_actuator_target(joint_name, target)
        for substep_index in range(max(1, substeps)):
            mujoco.mj_step(backend._model, backend._data)
            backend._apply_attachment()
            physics_steps += 1
            contacts: list[dict[str, Any]] = []
            step_geoms: set[str] = set()
            for contact_index in range(backend._data.ncon):
                contact = backend._data.contact[contact_index]
                geom_names = [
                    mujoco.mj_id2name(
                        backend._model, mujoco.mjtObj.mjOBJ_GEOM, int(geom_id)
                    )
                    or f"geom_{int(geom_id)}"
                    for geom_id in (contact.geom1, contact.geom2)
                ]
                if not any(name.endswith("grasp_cube") for name in geom_names) or not any(
                    name.startswith("robot/") for name in geom_names
                ):
                    continue
                force = np.zeros(6, dtype=float)
                mujoco.mj_contactForce(
                    backend._model, backend._data, contact_index, force
                )
                force_values = [float(value) for value in force]
                if not _finite(force_values):
                    continue
                normal_force = abs(force_values[0])
                tangential_force = math.hypot(force_values[1], force_values[2])
                penetration = max(0.0, -float(contact.dist))
                peak_normal_force_n = max(peak_normal_force_n, normal_force)
                peak_tangential_force_n = max(
                    peak_tangential_force_n, tangential_force
                )
                peak_penetration_m = max(peak_penetration_m, penetration)
                normal_impulse_ns += normal_force * scenario.runtime.physics_timestep_s
                tangential_impulse_ns += (
                    tangential_force * scenario.runtime.physics_timestep_s
                )
                robot_geoms = [name for name in geom_names if name.startswith("robot/")]
                step_geoms.update(robot_geoms)
                contact_geom_names.update(robot_geoms)
                contacts.append(
                    {
                        "contact_index": contact_index,
                        "geom_pair": geom_names,
                        "position_world_m": [float(value) for value in contact.pos],
                        "frame_world": [float(value) for value in contact.frame],
                        "distance_m": float(contact.dist),
                        "force_contact_frame": {
                            "force_n": force_values[:3],
                            "torque_nm": force_values[3:],
                            "normal_n": normal_force,
                            "tangential_norm_n": tangential_force,
                        },
                        "friction": [float(value) for value in contact.friction],
                        "solref": [float(value) for value in contact.solref],
                        "solimp": [float(value) for value in contact.solimp],
                    }
                )
            if not contacts:
                continue
            contact_physics_steps += 1
            bilateral = {
                "robot/fixed_finger_contact_mesh",
                "robot/moving_finger_contact_mesh",
            }.issubset(step_geoms)
            bilateral_physics_steps += int(bilateral)
            t_s = float(backend._data.time)
            first_contact_s = t_s if first_contact_s is None else first_contact_s
            last_contact_s = t_s
            positions, velocities, actuator_forces = joint_state()
            cube_joint = backend._free_joint_by_object.get("grasp_cube")
            cube_state: dict[str, Any] = {}
            if cube_joint:
                cube_joint_id = mujoco.mj_name2id(
                    backend._model, mujoco.mjtObj.mjOBJ_JOINT, cube_joint
                )
                qpos_address = int(backend._model.jnt_qposadr[cube_joint_id])
                qvel_address = int(backend._model.jnt_dofadr[cube_joint_id])
                cube_state = {
                    "position_world_m": [
                        float(value)
                        for value in backend._data.qpos[qpos_address : qpos_address + 3]
                    ],
                    "quaternion_wxyz": [
                        float(value)
                        for value in backend._data.qpos[qpos_address + 3 : qpos_address + 7]
                    ],
                    "linear_velocity_world_m_s": [
                        float(value)
                        for value in backend._data.qvel[qvel_address : qvel_address + 3]
                    ],
                    "angular_velocity_world_rad_s": [
                        float(value)
                        for value in backend._data.qvel[qvel_address + 3 : qvel_address + 6]
                    ],
                }
            write_record(
                {
                    "schema": "reva.mujoco_contact_sample.v1",
                    "t_s": t_s,
                    "physics_step": physics_steps,
                    "control_step": control_step,
                    "substep": substep_index,
                    "physics_timestep_s": scenario.runtime.physics_timestep_s,
                    "bilateral_finger_contact": bilateral,
                    "contacts": contacts,
                    "cube": cube_state,
                    "robot": {
                        "joint_positions_rad": positions,
                        "joint_velocities_rad_s": velocities,
                        "joint_targets_rad": current_targets,
                        "actuator_forces": actuator_forces,
                    },
                }
            )

    backend.step = instrumented_step
    try:
        with tempfile.TemporaryDirectory(prefix="reva-contact-replay-") as temp_dir:
            replay_result = run_episode(
                scenario=scenario,
                manifest=manifest,
                backend=backend,
                output_dir=Path(temp_dir),
                policy=policy,
            )
            replay_report = replay_result.to_report()
    finally:
        backend.step = original_step
        handle.close()

    reference_final = reference_report.get("final_object_poses", {}).get("grasp_cube", {})
    replay_final = replay_report.get("final_object_poses", {}).get("grasp_cube", {})
    reference_position = reference_final.get("position_xyz", []) if isinstance(reference_final, dict) else []
    replay_position = replay_final.get("position_xyz", []) if isinstance(replay_final, dict) else []
    final_position_error_m = None
    if len(reference_position) == 3 and len(replay_position) == 3:
        final_position_error_m = math.sqrt(
            sum((float(a) - float(b)) ** 2 for a, b in zip(reference_position, replay_position))
        )
    equrevaent = (
        replay_report.get("success") == reference_report.get("success")
        and replay_report.get("stop_reason") == reference_report.get("stop_reason")
        and replay_report.get("steps") == reference_report.get("steps")
        and final_position_error_m is not None
        and final_position_error_m <= 1e-9
    )
    summary = {
        "schema": "reva.mujoco_contact_telemetry_summary.v1",
        "episode_index": manifest.episode_index,
        "seed": manifest.seed,
        "capture": {
            "kind": "deterministic_diagnostic_replay",
            "physics_timestep_s": scenario.runtime.physics_timestep_s,
            "effective_sample_rate_hz": 1.0 / scenario.runtime.physics_timestep_s,
            "physics_steps_scanned": physics_steps,
            "contact_records": record_count,
            "contact_physics_steps": contact_physics_steps,
            "bilateral_contact_physics_steps": bilateral_physics_steps,
            "all_robot_cube_contacts_retained": True,
        },
        "contact": {
            "first_contact_s": first_contact_s,
            "last_contact_s": last_contact_s,
            "contact_duration_s": (
                None
                if first_contact_s is None or last_contact_s is None
                else last_contact_s - first_contact_s + scenario.runtime.physics_timestep_s
            ),
            "peak_normal_force_n": peak_normal_force_n,
            "peak_tangential_force_n": peak_tangential_force_n,
            "normal_impulse_ns": normal_impulse_ns,
            "tangential_impulse_ns": tangential_impulse_ns,
            "maximum_penetration_m": peak_penetration_m,
            "robot_contact_geoms": sorted(contact_geom_names),
        },
        "equrevaence": {
            "verified": equrevaent,
            "success_matches": replay_report.get("success") == reference_report.get("success"),
            "stop_reason_matches": replay_report.get("stop_reason") == reference_report.get("stop_reason"),
            "steps_match": replay_report.get("steps") == reference_report.get("steps"),
            "final_cube_position_error_m": final_position_error_m,
        },
        "artifacts": {
            "contact_telemetry_ndjson": {
                "path": output_path.name,
                "sha256": digest.hexdigest(),
                "bytes": output_path.stat().st_size,
                "record_count": record_count,
            }
        },
        "source_digests": {
            "scenario_sha256": _digest(scenario_path),
            "manifest_sha256": _digest(manifest_path),
            "reference_report_sha256": _digest(reference_report_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--reference-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    summary = record(
        args.scenario,
        args.manifest,
        args.reference_report,
        args.output,
        args.summary,
    )
    print(
        f"contact_telemetry={args.output} records={summary['capture']['contact_records']} "
        f"equrevaent={summary['equrevaence']['verified']}"
    )
    return 0 if summary["equrevaence"]["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
