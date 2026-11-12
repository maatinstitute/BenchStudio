#!/usr/bin/env python3
"""Optional real SmolVLA + MuJoCo closed-loop runner; requires pinned external assets."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import re
import sys
from pathlib import Path

from benchstudio.external_policy import PersistentExternalCommandPolicy
from benchstudio.hardware import ResourceRequest, plan_execution_resources, probe_hardware
from benchstudio.integrations.mujoco import MujocoSimulator
from benchstudio.runner import RunConfig, run_episodes


def _callback(path: str):
    module, separator, symbol = path.partition(":")
    if not separator or not module or not symbol:
        raise ValueError("callbacks must use module:function syntax")
    result = getattr(importlib.import_module(module), symbol)
    if not callable(result):
        raise ValueError("callback must be callable")
    source_path = inspect.getsourcefile(result)
    if not source_path or not Path(source_path).is_file():
        raise ValueError("callback must have a readable source file")
    return result, hashlib.sha256(Path(source_path).read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Pinned SmolVLA + MuJoCo visual baseline")
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--camera-name", required=True)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument(
        "--map-input", required=True,
        help="module:function mapping MuJoCo state + RGB to checkpoint policy_batch",
    )
    parser.add_argument(
        "--success-fn", required=True,
        help="module:function accepting (MjModel, MjData) and returning bool",
    )
    parser.add_argument("--device", required=True, help="cpu, cuda:N, or mps")
    parser.add_argument("--estimated-host-mib", type=int, required=True)
    parser.add_argument("--estimated-gpu-mib", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("runs/visual-smolvla"))
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--action-prefix", type=int, default=1)
    args = parser.parse_args()

    if not args.scene.is_file() or not args.checkpoint.is_dir():
        parser.error("--scene must be an MJCF file and --checkpoint an existing local directory")
    if re.fullmatch(r"[0-9a-f]{64}", args.checkpoint_sha256) is None:
        parser.error("--checkpoint-sha256 must be a lowercase SHA-256")
    if any(
        x < 1 for x in (
            args.estimated_host_mib, args.width, args.height, args.episodes,
            args.steps, args.action_prefix,
        )
    ) or args.estimated_gpu_mib < 0:
        parser.error("memory estimates must be non-negative; other counts must be positive")
    gpu = re.fullmatch(r"cuda:(\d+)", args.device)
    if gpu is None and args.device not in {"cpu", "mps"}:
        parser.error("--device must be cpu, mps or cuda:N")
    if (gpu is None and args.estimated_gpu_mib != 0) or (
        gpu is not None and args.estimated_gpu_mib == 0
    ):
        parser.error("cuda:N requires --estimated-gpu-mib; CPU/MPS uses no NVIDIA estimate")

    mapper, mapper_sha = _callback(args.map_input)
    scorer, scorer_sha = _callback(args.success_fn)
    admission = plan_execution_resources(
        ResourceRequest(
            host_memory_bytes=args.estimated_host_mib * 1024 * 1024,
            gpu_memory_bytes=args.estimated_gpu_mib * 1024 * 1024,
            gpu_index=int(gpu.group(1)) if gpu is not None else None,
        ),
        probe_hardware(),
    )
    scene_sha = hashlib.sha256(args.scene.read_bytes()).hexdigest()

    def build_observation(raw):
        policy_batch = mapper(raw)
        if not isinstance(policy_batch, dict) or not policy_batch:
            raise ValueError("map-input must return a nonempty policy_batch mapping")
        # Rendered image is mapped once; do not export it a second time.
        return {
            "policy_batch": policy_batch,
            "qpos": raw["qpos"],
            "qvel": raw["qvel"],
            "ctrl": raw["ctrl"],
        }

    simulator = MujocoSimulator(
        args.scene,
        camera_name=args.camera_name,
        camera_width=args.width,
        camera_height=args.height,
        observation_fn=build_observation,
        success_fn=scorer,
        max_steps=args.steps,
    )
    runtime_script = Path(__file__).parents[1] / "external_runtime" / "lerobot_smolvla_policy.py"
    policy = PersistentExternalCommandPolicy(
        [sys.executable, str(runtime_script)],
        policy_id="smolvla_external_mmap",
        tensor_transport="mmap",
        device=args.device,
        timeout_s=120,
        environment={
            "BENCHSTUDIO_LEROBOT_CHECKPOINT": str(args.checkpoint.resolve()),
            "BENCHSTUDIO_LEROBOT_CHECKPOINT_SHA256": args.checkpoint_sha256,
        },
    )
    summary = run_episodes(
        policy,
        simulator,
        RunConfig(
            episodes=args.episodes,
            max_episode_steps=args.steps,
            action_prefix=args.action_prefix,
            denoising_steps=None,
            resource_preflight=admission.to_dict(),
            model_reference={
                "checkpoint_sha256": args.checkpoint_sha256,
                "scene_sha256": scene_sha,
                "observation_mapping_sha256": mapper_sha,
                "success_fn_sha256": scorer_sha,
                "device": args.device,
                "transport": "mmap",
            },
        ),
        args.output,
    )
    print(json.dumps({
        "status": summary["campaign_status"],
        "scheduled_episode_count": summary["scheduled_episode_count"],
        "completed_episode_count": summary["completed_episode_count"],
        "success_count": summary["success_count"],
        "output": str(args.output),
        "provenance": "real_runtime_only_if_external_checkpoint_and_callbacks_qualified",
    }, sort_keys=True))
    return 0 if summary["campaign_status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
