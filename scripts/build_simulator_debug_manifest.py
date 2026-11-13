#!/usr/bin/env python3
"""Bind shared scenario parameters and per-simulator outcomes for UI debugging."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from backend.services.scenario_loader import load_scenario, resolve_scenario_asset_path

    scenario = load_scenario(args.scenario)
    scenario_dir = args.scenario if args.scenario.is_dir() else args.scenario.parent
    scenario_file = scenario_dir / "scenario.yaml"
    world_file = resolve_scenario_asset_path(args.scenario, scenario.world.package)
    robot_file = resolve_scenario_asset_path(args.scenario, scenario.robot.urdf or "")
    policy_file = resolve_scenario_asset_path(
        args.scenario, str(scenario.policy.params.get("waypoints_file", ""))
    )
    run = json.loads(args.run.read_text(encoding="utf-8"))
    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    requested = set(run.get("sims", []))
    summaries = comparison.get("summary", {})
    errors = comparison.get("errors", {})
    packages = run.get("orchestrator_environment", {}).get("packages", {})

    backends = {}
    for backend_id, package_name in (("mujoco", "mujoco"), ("genesis", "genesis")):
        summary = summaries.get(backend_id, {})
        backend_errors = errors.get(backend_id, [])
        if int(summary.get("completed", 0) or 0) > 0:
            status = "evaluated"
        elif backend_id in requested:
            status = "failed"
        else:
            status = "not_run"
        completed = int(summary.get("completed", 0) or 0)
        backends[backend_id] = {
            "status": status,
            "requested": backend_id in requested,
            "package_available": importlib.util.find_spec(package_name) is not None,
            "package_version": packages.get(package_name),
            "episodes": int(summary.get("episodes", 0) or 0),
            "completed": completed,
            "success_count": int(summary.get("success_count", 0) or 0),
            "success_rate": summary.get("success_rate") if completed else None,
            "mean_sim_time_s": summary.get("mean_time_to_success_s"),
            "mean_wall_time_s": summary.get("mean_wall_time_s"),
            "errors": backend_errors,
        }

    payload = {
        "schema": "ival.simulator_debug.v1",
        "scenario_id": scenario.scenario_id,
        "shared_parameters": {
            "physics_timestep_s": scenario.runtime.physics_timestep_s,
            "control_hz": scenario.runtime.control_hz,
            "checker_interval_steps": scenario.runtime.checker_interval_steps,
            "max_episode_steps": scenario.runtime.max_episode_steps,
            "grasp_attach": scenario.runtime.grasp_attach,
            "attach_link": scenario.runtime.attach_link,
            "episodes": scenario.evaluation.episodes,
            "seeds": scenario.evaluation.seeds,
        },
        "input_digests": {
            "scenario_sha256": _digest(scenario_file),
            "world_sha256": _digest(world_file),
            "robot_sha256": _digest(robot_file),
            "policy_sha256": _digest(policy_file),
        },
        "backends": backends,
        "divergence": comparison.get("divergence", {}),
    }
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"simulator_debug={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
