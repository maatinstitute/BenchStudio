#!/usr/bin/env python3
"""Freeze the planned episode identities and object poses for a REVA study."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path


def build_manifest(study: dict) -> dict:
    study_id = str(study["study_id"])
    count = int(study["episodes_per_simulator"])
    randomization = study.get("randomization", {})
    jitter = randomization.get("cube_position_jitter_m", [0.0, 0.0, 0.0])
    yaw_jitter = float(randomization.get("cube_yaw_jitter_rad", 0.0))
    pairing = study.get("pairing", {})
    pilot_seeds = pairing.get("pilot_seeds", []) if isinstance(pairing, dict) else []
    pilot_design = study.get("pilot_design", {})
    pilot_conditions = pilot_design.get("conditions", []) if isinstance(pilot_design, dict) else []
    center = (0.27, 0.0, 0.0225)
    episodes = []
    for index in range(count):
        digest = hashlib.sha256(f"{study_id}:{index}".encode()).hexdigest()
        seed = (
            int(pilot_seeds[index])
            if index < len(pilot_seeds)
            else int(digest[:8], 16) & 0x7FFFFFFF
        )
        generator = random.Random(seed)
        position = [
            round(center[axis] + generator.uniform(-float(jitter[axis]), float(jitter[axis])), 9)
            for axis in range(3)
        ]
        yaw = round(generator.uniform(-yaw_jitter, yaw_jitter), 9)
        condition = pilot_conditions[index] if index < len(pilot_conditions) else {}
        condition_id = str(condition.get("id", "production_candidate")) if isinstance(condition, dict) else "production_candidate"
        episodes.append({
            "episode_id": f"episode-{index:03d}",
            "episode_index": index,
            "seed": seed,
            "object_placements": {
                "grasp_cube": {
                    "position_xyz": position,
                    "rotation_rpy_rad": [0.0, 0.0, yaw],
                }
            },
            "policy_condition": condition_id,
            "status": "preflight" if index < len(pilot_seeds) else "not_scheduled",
        })
    payload = {
        "schema": "reva.study_manifest.v1",
        "study_id": study_id,
        "simulator": "mujoco",
        "episode_count": count,
        "seed_derivation": "sha256(study_id, episode_index)",
        "episodes": episodes,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    study = json.loads(args.study.read_text(encoding="utf-8"))
    payload = build_manifest(study)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"study_manifest={args.output} episodes={payload['episode_count']} digest={payload['manifest_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
