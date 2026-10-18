from __future__ import annotations

import argparse
from pathlib import Path

from .adapters import default_registry
from .campaigns import (
    CampaignExecutor,
    LocalArtifactStore,
    compile_campaign_spec,
    load_campaign_document,
)
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
        help=(
            "Compile a JSON/YAML benchstudio.campaign.v1 specification instead of running the mock."
        ),
    )
    parser.add_argument(
        "--plan-output",
        type=Path,
        default=Path("campaign-plan.json"),
        help="Destination for a compiled campaign plan.",
    )
    parser.add_argument(
        "--execute-mock",
        action="store_true",
        help="Execute a compiled campaign with the deterministic mock adapters.",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Audit the executed campaign ledger and print its claim status.",
    )
    parser.add_argument(
        "--archive-output",
        type=Path,
        help="Write a deterministic immutable archive of the executed campaign evidence.",
    )
    parser.add_argument(
        "--artifact-store",
        type=Path,
        help="Publish the executed campaign bundle to a local content-addressed store.",
    )
    args = parser.parse_args()
    if args.campaign_spec is not None:
        spec = load_campaign_document(args.campaign_spec)
        plan = compile_campaign_spec(spec)
        plan.write(args.plan_output)
        print(
            f"compiled_plan={args.plan_output} attempts={len(plan.attempts)} "
            f"digest={plan.plan_digest_sha256}"
        )
        if args.execute_mock:
            executor = CampaignExecutor(
                plan,
                args.output,
                lambda _: MockPolicy(),
                lambda _: MockSimulator(),
                adapter_registry=default_registry(),
            )
            summary = executor.run()
            print(
                f"campaign_status=completed committed={len(summary.committed_attempt_ids)} "
                f"missing={len(summary.missing_attempt_ids)}"
            )
            if args.audit:
                audit = executor.audit()
                print(
                    f"audit_status={audit.claim.status} "
                    f"attempts_complete={audit.attempts_complete} "
                    f"evidence_verified={audit.evidence_verified}"
                )
            if args.archive_output is not None:
                archive = executor.archive(args.archive_output)
                print(
                    f"archive_output={archive['path']} archive_sha256={archive['sha256']} "
                    f"archive_bytes={archive['bytes']}"
                )
            if args.artifact_store is not None:
                reference = executor.publish_artifact(LocalArtifactStore(args.artifact_store))
                print(
                    f"artifact_uri={reference['uri']} artifact_sha256={reference['digest_sha256']} "
                    f"artifact_bytes={reference['bytes']}"
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
