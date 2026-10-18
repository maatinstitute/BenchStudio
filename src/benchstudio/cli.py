from __future__ import annotations

import argparse
import json
from pathlib import Path

from .campaigns import compile_campaign_spec
from .mock import MockPolicy, MockSimulator
from .runner import RunConfig, run_episodes


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a BenchStudio temporal-fidelity evaluation.")
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("runs/smoke"))
    parser.add_argument("--action-prefix", type=int, default=2)
    parser.add_argument("--denoising-steps", type=int, default=2)
    parser.add_argument(
        "--campaign-spec",
        type=Path,
        help="Compile a JSON benchstudio.campaign.v1 specification instead of running the mock.",
    )
    parser.add_argument(
        "--plan-output",
        type=Path,
        default=Path("campaign-plan.json"),
        help="Destination for a compiled campaign plan.",
    )
    args = parser.parse_args()
    if args.campaign_spec is not None:
        spec = json.loads(args.campaign_spec.read_text(encoding="utf-8"))
        plan = compile_campaign_spec(spec)
        plan.write(args.plan_output)
        print(
            f"compiled_plan={args.plan_output} attempts={len(plan.attempts)} "
            f"digest={plan.plan_digest_sha256}"
        )
        return 0
    config = RunConfig(
        episodes=args.episodes,
        action_prefix=args.action_prefix,
        denoising_steps=args.denoising_steps,
    )
    summary = run_episodes(MockPolicy(), MockSimulator(), config, args.output)
    print(
        f"scheduled_success_rate={summary['scheduled_success_rate']:.3f} "
        f"episodes={summary['episode_count']} status={summary['campaign_status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
