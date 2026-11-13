#!/usr/bin/env python3
"""Prepare a traceable policy/scenario variant for the SO-101 pilot cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_variant(
    source: Path,
    output: Path,
    *,
    condition_id: str,
    label: str,
    time_scale: float,
    shoulder_pan_offset_rad: float,
    max_episode_steps: int,
) -> dict:
    if output.exists():
        raise ValueError(f"refusing to overwrite pilot variant: {output}")
    if time_scale <= 0:
        raise ValueError("time_scale must be positive")
    if max_episode_steps <= 0:
        raise ValueError("max_episode_steps must be positive")
    shutil.copytree(source, output)

    policy_path = output / "waypoints.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    waypoints = policy.get("waypoints")
    if not isinstance(waypoints, list) or not waypoints:
        raise ValueError("waypoints.json must contain waypoints")
    for waypoint in waypoints:
        if not isinstance(waypoint, dict):
            continue
        original_time = float(waypoint.get("time_s", 0.0) or 0.0)
        waypoint["time_s"] = round(original_time * time_scale, 6)
        joints = waypoint.get("joints")
        if original_time > 0 and isinstance(joints, dict) and "shoulder_pan" in joints:
            joints["shoulder_pan"] = round(
                float(joints["shoulder_pan"]) + shoulder_pan_offset_rad, 6
            )
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")

    scenario_path = output / "scenario.yaml"
    scenario_text = scenario_path.read_text(encoding="utf-8")
    scenario_text, step_changes = re.subn(
        r"(?m)^(\s*max_episode_steps:)\s*\d+\s*$",
        rf"\g<1> {max_episode_steps}",
        scenario_text,
    )
    timeout_seconds = max_episode_steps / 50.0
    scenario_text, timeout_changes = re.subn(
        r"(?m)^(\s*timeout_sim_seconds:)\s*[0-9.]+\s*$",
        rf"\g<1> {timeout_seconds:g}",
        scenario_text,
    )
    if step_changes != 1 or timeout_changes != 1:
        raise ValueError("scenario runtime fields were not uniquely found")
    scenario_path.write_text(scenario_text, encoding="utf-8")

    condition = {
        "schema": "ival.pilot_condition.v1",
        "id": condition_id,
        "label": label,
        "changed_parameters": {
            "policy.time_scale": time_scale,
            "policy.shoulder_pan_offset_rad": shoulder_pan_offset_rad,
            "runtime.max_episode_steps": max_episode_steps,
        },
        "policy_sha256": _digest(policy_path),
        "scenario_sha256": _digest(scenario_path),
    }
    (output / "pilot-condition.json").write_text(
        json.dumps(condition, indent=2) + "\n", encoding="utf-8"
    )
    return condition


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--condition-id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--shoulder-pan-offset-rad", type=float, default=0.0)
    parser.add_argument("--max-episode-steps", type=int, default=400)
    args = parser.parse_args()
    condition = prepare_variant(
        args.source,
        args.output,
        condition_id=args.condition_id,
        label=args.label,
        time_scale=args.time_scale,
        shoulder_pan_offset_rad=args.shoulder_pan_offset_rad,
        max_episode_steps=args.max_episode_steps,
    )
    print(f"pilot_variant={args.output} policy={condition['policy_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
