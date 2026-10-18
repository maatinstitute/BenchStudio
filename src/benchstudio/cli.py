from __future__ import annotations

import argparse
from pathlib import Path

from .mock import MockPolicy, MockSimulator
from .runner import RunConfig, run_episodes


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a BenchStudio temporal-fidelity evaluation.")
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("runs/smoke"))
    parser.add_argument("--action-prefix", type=int, default=2)
    parser.add_argument("--denoising-steps", type=int, default=2)
    args = parser.parse_args()
    config = RunConfig(
        episodes=args.episodes,
        action_prefix=args.action_prefix,
        denoising_steps=args.denoising_steps,
    )
    summary = run_episodes(MockPolicy(), MockSimulator(), config, args.output)
    print(f"success_rate={summary['success_rate']:.3f} episodes={summary['episode_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
