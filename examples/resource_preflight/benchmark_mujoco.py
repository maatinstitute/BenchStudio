"""Run a genuine MuJoCo stepping baseline through IVal's existing runner.

It measures the execution path, not VLA accuracy or physics parity with Isaac Sim.
Install with: uv sync --locked --extra mujoco
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

from ival.contracts import ActionChunk
from ival.hardware import ResourceRequest, plan_execution_resources, probe_hardware
from ival.integrations.mujoco import MujocoSimulator
from ival.runner import RunConfig, run_episodes


class ZeroMotorPolicy:
    policy_id = "slider_zero_motor_baseline"

    def reset(self, *, seed: int) -> None:
        del seed

    def predict(self, observation, *, denoising_steps):
        del observation, denoising_steps
        return ActionChunk(((0.0,),))


def _peak_rss() -> dict[str, int]:
    try:
        import resource
    except ImportError:
        return {}
    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is KiB on Linux and bytes on macOS.
    return {"peak_host_rss_bytes": int(maximum * (1024 if platform.system() == "Linux" else 1))}


def main() -> int:
    parser = argparse.ArgumentParser(description="MuJoCo CPU physics resource baseline")
    parser.add_argument("--output", type=Path, default=Path("runs/resource-slider"))
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--estimated-host-mib", type=int, default=128)
    args = parser.parse_args()
    if args.episodes < 1 or args.steps < 1 or args.estimated_host_mib < 1:
        parser.error("episodes, steps and estimated-host-mib must be positive")

    request = ResourceRequest(host_memory_bytes=args.estimated_host_mib * 1024 * 1024)
    preflight = plan_execution_resources(request, probe_hardware())
    import mujoco

    timestep = 0.005  # Frozen by slider.xml.
    simulator = MujocoSimulator(
        Path(__file__).with_name("slider.xml"),
        max_steps=args.steps,
        success_fn=lambda _model, data: data.time + 1e-12 >= args.steps * timestep,
    )
    start = time.perf_counter()
    result = run_episodes(
        ZeroMotorPolicy(),
        simulator,
        RunConfig(
            episodes=args.episodes,
            action_prefix=1,
            max_episode_steps=args.steps,
            resource_preflight=preflight.to_dict(),
        ),
        args.output,
        resource_sampler=_peak_rss,
    )
    wall_seconds = time.perf_counter() - start
    steps = sum(episode["steps"] for episode in result["episodes"])
    simulated_seconds = steps * timestep
    print(json.dumps({
        "schema": "ival.mujoco_resource_baseline.v1",
        "physics_backend": "mujoco",
        "mujoco_version": mujoco.__version__,
        "policy": "zero_motor_diagnostic_not_vla",
        "steps": steps,
        "simulated_seconds": simulated_seconds,
        "wall_seconds": wall_seconds,
        "sim_seconds_per_wall_second": (simulated_seconds / wall_seconds if wall_seconds else None),
        "max_observed_peak_rss_bytes": max(
            (ep["resource_metrics"].get("peak_host_rss_bytes", 0) for ep in result["episodes"]),
            default=0,
        ),
        "output": str(args.output),
    }, indent=2, sort_keys=True))
    return 0 if result["campaign_status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
