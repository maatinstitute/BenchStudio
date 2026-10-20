#!/usr/bin/env python3
"""Bind heterogeneous pilot executions into one inspectable cohort artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_cohort(run_root: Path, output: Path) -> dict:
    definitions = [
        ("baseline", "Baseline", 0, run_root / "scenario", run_root / "mujoco" / "episode-0", {"control": "baseline"}),
        ("fast_approach", "Fast approach", 1, run_root / "pilot-scenarios" / "fast-approach", run_root / "pilot" / "fast-approach", {}),
        ("slow_approach", "Slow approach", 2, run_root / "pilot-scenarios" / "slow-approach", run_root / "recovery" / "episode-2" / "attempt-1", {"policy.approach_duration_s": 2.4}),
        ("lateral_offset", "Lateral offset", 3, run_root / "pilot-scenarios" / "lateral-offset", run_root / "pilot" / "lateral-offset", {}),
    ]
    entries = []
    for condition_id, label, episode_index, scenario_dir, evidence_dir, defaults in definitions:
        report_path = evidence_dir / "report.json"
        analysis_path = evidence_dir / "contact-analysis.json"
        video_path = evidence_dir / "episode.mp4"
        policy_path = scenario_dir / "waypoints.json"
        manifest_path = run_root / "manifests" / f"episode-{episode_index}.json"
        required = (report_path, analysis_path, video_path, policy_path, manifest_path)
        if not all(path.is_file() for path in required):
            continue
        report = _load(report_path)
        analysis = _load(analysis_path)
        manifest = _load(manifest_path)
        condition_path = scenario_dir / "pilot-condition.json"
        condition = _load(condition_path) if condition_path.is_file() else {
            "id": condition_id,
            "label": label,
            "changed_parameters": defaults,
        }
        entries.append({
            "condition_id": condition_id,
            "label": label,
            "episode_index": episode_index,
            "seed": manifest.get("seed"),
            "success": report.get("success"),
            "stop_reason": report.get("stop_reason"),
            "steps": report.get("steps"),
            "sim_time_s": report.get("sim_time_s"),
            "failure_class": analysis.get("failure_class"),
            "changed_parameters": condition.get("changed_parameters", {}),
            "policy_sha256": _digest(policy_path),
            "video": {
                "path": str(video_path.relative_to(run_root)),
                "sha256": _digest(video_path),
                "bytes": video_path.stat().st_size,
            },
            "report_path": str(report_path.relative_to(run_root)),
            "analysis_path": str(analysis_path.relative_to(run_root)),
        })
    payload = {
        "schema": "benchstudio.pilot_cohort.v1",
        "purpose": "parameter and instrumentation validation; not a population estimate",
        "entries": entries,
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_cohort(args.run_root, args.output)
    print(f"pilot_cohort={args.output} entries={len(payload['entries'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
