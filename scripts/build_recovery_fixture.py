#!/usr/bin/env python3
"""Prepare and bind a causal policy-intervention pair for the robot demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def prepare_probe(source: Path, output: Path, approach_duration_s: float) -> None:
    if output.exists():
        raise ValueError(f"refusing to overwrite intervention scenario: {output}")
    shutil.copytree(source, output)
    policy_path = output / "waypoints.json"
    policy = _load_json(policy_path)
    waypoints = policy.get("waypoints", [])
    if not isinstance(waypoints, list):
        raise ValueError("waypoints.json must contain a waypoint list")
    approach = next(
        (waypoint for waypoint in waypoints if waypoint.get("label") == "approach"),
        None,
    )
    descend = next(
        (waypoint for waypoint in waypoints if waypoint.get("label") == "descend"),
        None,
    )
    if not isinstance(approach, dict) or not isinstance(descend, dict):
        raise ValueError("policy must contain approach and descend waypoints")
    approach_time_s = float(approach.get("time_s", 0.0))
    descend_time_s = float(descend.get("time_s", 0.0))
    baseline_duration_s = descend_time_s - approach_time_s
    if approach_duration_s <= baseline_duration_s:
        raise ValueError("intervention approach duration must exceed the baseline")
    shift_s = approach_duration_s - baseline_duration_s
    for waypoint in waypoints:
        if isinstance(waypoint, dict) and float(waypoint.get("time_s", 0.0)) >= descend_time_s:
            waypoint["time_s"] = round(float(waypoint["time_s"]) + shift_s, 6)
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    change = {
        "schema": "ival.robot_intervention.v1",
        "kind": "slow_approach",
        "parameter": "policy.approach_duration_s",
        "baseline_value": baseline_duration_s,
        "intervention_value": approach_duration_s,
        "unit": "s",
        "causal_target": "reduce pre-close contact force and cube displacement",
        "policy_changed": True,
    }
    (output / "intervention.json").write_text(
        json.dumps(change, indent=2), encoding="utf-8"
    )


def bind_pair(
    *,
    output: Path,
    episode_index: int,
    manifest_path: Path,
    intervention_path: Path,
    failed_dir: Path,
    recovered_dir: Path,
    failed_policy_path: Path,
    recovered_policy_path: Path,
) -> None:
    manifest = _load_json(manifest_path)
    intervention = _load_json(intervention_path)
    failed_report_path = failed_dir / "report.json"
    recovered_report_path = recovered_dir / "report.json"
    failed = _load_json(failed_report_path)
    recovered = _load_json(recovered_report_path)
    if failed.get("success") is not False:
        raise ValueError("the baseline attempt did not produce a failure")
    failed_policy_sha256 = _digest(failed_policy_path)
    recovered_policy_sha256 = _digest(recovered_policy_path)
    if failed_policy_sha256 == recovered_policy_sha256:
        raise ValueError("intervention must change the frozen policy")

    def attempt_payload(attempt: int, directory: Path, report: dict) -> dict:
        files = {}
        for name in (
            "report.json",
            "trace.ndjson",
            "decisions.ndjson",
            "episode.mp4",
            "contact-analysis.json",
            "contact-telemetry.ndjson",
            "contact-telemetry-summary.json",
        ):
            path = directory / name
            if path.is_file():
                files[name] = {
                    "path": str(path.relative_to(output.parent)),
                    "sha256": _digest(path),
                    "bytes": path.stat().st_size,
                }
        return {
            "attempt": attempt,
            "success": report.get("success"),
            "stop_reason": report.get("stop_reason"),
            "steps": report.get("steps"),
            "sim_time_s": report.get("sim_time_s"),
            "files": files,
        }

    recovered_success = recovered.get("success") is True
    baseline_analysis_path = failed_dir / "contact-analysis.json"
    intervention_analysis_path = recovered_dir / "contact-analysis.json"
    baseline_analysis = _load_json(baseline_analysis_path) if baseline_analysis_path.is_file() else {}
    intervention_analysis = _load_json(intervention_analysis_path) if intervention_analysis_path.is_file() else {}

    def diagnostic_value(payload: dict, *keys: str) -> float | None:
        value: object = payload
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return float(value) if isinstance(value, (int, float)) else None

    baseline_force = diagnostic_value(
        baseline_analysis, "physics_contact_telemetry", "contact", "peak_normal_force_n"
    )
    intervention_force = diagnostic_value(
        intervention_analysis, "physics_contact_telemetry", "contact", "peak_normal_force_n"
    )
    baseline_displacement = diagnostic_value(
        baseline_analysis, "motion", "horizontal_displacement_m"
    )
    intervention_displacement = diagnostic_value(
        intervention_analysis, "motion", "horizontal_displacement_m"
    )
    payload = {
        "schema": "ival.robot_intervention_pair.v1",
        "backend": "mujoco",
        "episode_index": episode_index,
        "seed": manifest.get("seed"),
        "status": "recovered" if recovered_success else "lift_still_failed",
        "policy_changed": True,
        "policy_binding": {
            "failed_attempt_sha256": failed_policy_sha256,
            "recovered_attempt_sha256": recovered_policy_sha256,
            "unchanged": False,
        },
        "intervention": intervention,
        "effect": {
            "baseline_failure_class": baseline_analysis.get("failure_class"),
            "intervention_failure_class": intervention_analysis.get("failure_class"),
            "peak_normal_force_n": {
                "baseline": baseline_force,
                "intervention": intervention_force,
                "delta": (
                    intervention_force - baseline_force
                    if baseline_force is not None and intervention_force is not None
                    else None
                ),
            },
            "horizontal_displacement_m": {
                "baseline": baseline_displacement,
                "intervention": intervention_displacement,
                "delta": (
                    intervention_displacement - baseline_displacement
                    if baseline_displacement is not None and intervention_displacement is not None
                    else None
                ),
            },
        },
        "attempts": [
            attempt_payload(0, failed_dir, failed),
            attempt_payload(1, recovered_dir, recovered),
        ],
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--approach-duration-s", type=float, default=2.4)

    bind = subparsers.add_parser("bind")
    bind.add_argument("--output", type=Path, required=True)
    bind.add_argument("--episode-index", type=int, required=True)
    bind.add_argument("--manifest", type=Path, required=True)
    bind.add_argument("--intervention", type=Path, required=True)
    bind.add_argument("--failed-dir", type=Path, required=True)
    bind.add_argument("--recovered-dir", type=Path, required=True)
    bind.add_argument("--failed-policy", type=Path, required=True)
    bind.add_argument("--recovered-policy", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        prepare_probe(args.source, args.output, args.approach_duration_s)
    else:
        bind_pair(
            output=args.output,
            episode_index=args.episode_index,
            manifest_path=args.manifest,
            intervention_path=args.intervention,
            failed_dir=args.failed_dir,
            recovered_dir=args.recovered_dir,
            failed_policy_path=args.failed_policy,
            recovered_policy_path=args.recovered_policy,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
