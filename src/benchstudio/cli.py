from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters import default_registry
from .campaigns import (
    CampaignExecutor,
    LocalArtifactStore,
    compile_campaign_spec,
    load_campaign_document,
)
from .mock import MockPolicy, MockSimulator
from .model_adapters import default_model_registry
from .runner import RunConfig, run_episodes


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _mock_policy_factory(_attempt):
    return MockPolicy()


def _mock_simulator_factory(_attempt):
    return MockSimulator()


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
    execution_group = parser.add_mutually_exclusive_group()
    execution_group.add_argument(
        "--execute-mock",
        action="store_true",
        help="Execute a compiled campaign with the deterministic mock adapters.",
    )
    execution_group.add_argument(
        "--execute-registry",
        action="store_true",
        help="Execute adapters declared in the frozen campaign specification.",
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
    parser.add_argument(
        "--workers",
        type=_positive_int,
        default=1,
        help="Number of lease-owning workers for a compiled campaign (default: 1).",
    )
    parser.add_argument(
        "--readiness",
        action="store_true",
        help="Print dependency readiness and declared capabilities for available adapters.",
    )
    args = parser.parse_args()
    if args.readiness:
        simulator_registry = default_registry(discover_external=False)
        model_registry = default_model_registry(discover_external=False)
        simulators = [
            simulator_registry.readiness(descriptor.simulator_id)
            for descriptor in simulator_registry.list()
        ]
        models = [
            {
                **(readiness := model_registry.readiness(descriptor.adapter_id)),
                "capabilities": readiness["capabilities"].to_dict(),
            }
            for descriptor in model_registry.list()
        ]
        print(json.dumps({"simulators": simulators, "models": models}, sort_keys=True))
        return 0
    if args.campaign_spec is not None:
        spec = load_campaign_document(args.campaign_spec)
        plan = compile_campaign_spec(spec)
        plan.write(args.plan_output)
        print(
            f"compiled_plan={args.plan_output} attempts={len(plan.attempts)} "
            f"digest={plan.plan_digest_sha256}"
        )
        if args.execute_mock or args.execute_registry:
            if args.execute_registry:
                environments = plan.protocol.get("S", {}).get("environments", [])
                enabled_without_adapter = [
                    item.get("id", "<unknown>")
                    for item in environments
                    if isinstance(item, dict)
                    and item.get("enabled", item.get("kind") != "physical")
                    and not item.get("adapter")
                ]
                if enabled_without_adapter:
                    raise ValueError(
                        "--execute-registry requires adapters for enabled environments: "
                        + ", ".join(enabled_without_adapter)
                    )
                model_declared = (plan.protocol.get("M", {}) or {}).get("adapter")
                policy_factory = None if model_declared else _mock_policy_factory
                simulator_factory = None
                model_registry = default_model_registry()
            else:
                policy_factory = _mock_policy_factory
                simulator_factory = _mock_simulator_factory
                model_registry = None
            executor = CampaignExecutor(
                plan,
                args.output,
                policy_factory,
                simulator_factory,
                adapter_registry=default_registry(),
                model_registry=model_registry,
            )
            summary = executor.run_parallel(args.workers) if args.workers > 1 else executor.run()
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
