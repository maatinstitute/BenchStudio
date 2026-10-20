#!/usr/bin/env python3
"""Prepare and bind a real failed-attempt/recovery pair for the robot demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def prepare_probe(source: Path, output: Path, max_steps: int) -> None:
    if output.exists():
        raise ValueError(f"refusing to overwrite recovery scenario: {output}")
    shutil.copytree(source, output)
    scenario_path = output / "scenario.yaml"
    scenario_text = scenario_path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^(\s*)max_episode_steps:\s*(\d+)\s*$", scenario_text)
    if match is None:
        raise ValueError("scenario.yaml must declare runtime.max_episode_steps")
    original_steps = int(match.group(2))
    if max_steps <= 0 or max_steps >= original_steps:
        raise ValueError("recovery probe max steps must be positive and below the protocol limit")
    scenario_text = (
        scenario_text[: match.start()]
        + f"{match.group(1)}max_episode_steps: {max_steps}"
        + scenario_text[match.end() :]
    )
    scenario_path.write_text(scenario_text, encoding="utf-8")
    change = {
        "schema": "benchstudio.recovery_intervention.v1",
        "kind": "extend_episode_horizon",
        "parameter": "runtime.max_episode_steps",
        "failed_value": max_steps,
        "recovered_value": original_steps,
        "policy_changed": False,
    }
    (output / "recovery-intervention.json").write_text(
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
        raise ValueError("the recovery probe did not produce a failed attempt")
    if recovered.get("success") is not True:
        raise ValueError("the recovery attempt did not pass")
    failed_policy_sha256 = _digest(failed_policy_path)
    recovered_policy_sha256 = _digest(recovered_policy_path)
    if failed_policy_sha256 != recovered_policy_sha256:
        raise ValueError("recovery changed the frozen policy")

    def attempt_payload(attempt: int, directory: Path, report: dict) -> dict:
        files = {}
        for name in ("report.json", "trace.ndjson", "decisions.ndjson", "episode.mp4"):
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

    payload = {
        "schema": "benchstudio.robot_recovery.v1",
        "backend": "mujoco",
        "episode_index": episode_index,
        "seed": manifest.get("seed"),
        "status": "recovered",
        "policy_changed": False,
        "policy_binding": {
            "failed_attempt_sha256": failed_policy_sha256,
            "recovered_attempt_sha256": recovered_policy_sha256,
            "unchanged": True,
        },
        "intervention": intervention,
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
    prepare.add_argument("--max-steps", type=int, default=125)

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
        prepare_probe(args.source, args.output, args.max_steps)
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
