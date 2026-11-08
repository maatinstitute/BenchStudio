from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from .adapters import default_registry
from .analysis import (
    ClaimType,
    audit_campaign_directory,
    audit_evaluation_acceptance,
    compare_policy_trace_files,
    load_smolvla_deployment_evidence,
    load_recovery_records,
    load_transfer_records,
    summarize_recovery_outcomes,
    summarize_transfer_fidelity,
    write_recovery_report,
    write_transfer_fidelity_report,
)
from .campaigns import (
    CampaignExecutor,
    HttpArtifactStore,
    Intervention,
    LocalArtifactStore,
    compile_campaign_spec,
    compile_counterfactual_plan,
    compile_refinement_source_plan,
    load_campaign_document,
    load_frozen_campaign_plan,
    load_outcome_plan,
    retrieve_campaign_archive,
    verify_campaign_archive,
)
from .compare import build_campaign_comparison_report
from .evidence import verify_artifact_manifest
from .integrations.robochallenge import audit_robochallenge_wire_records
from .mock import MockPolicy, MockSimulator
from .model_adapters import default_model_registry
from .runner import RunConfig, run_episodes
from .scenarios import verify_scenario_archive
from .source_snapshot import verify_source_snapshot


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _mock_policy_factory(_attempt):
    return MockPolicy()


def _mock_simulator_factory(_attempt):
    return MockSimulator()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="benchstudio campaign",
        description="Run a BenchStudio temporal-fidelity evaluation.",
    )
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
        "--frozen-plan",
        type=Path,
        help="Load an existing frozen campaign plan for recovery or direct execution.",
    )
    parser.add_argument(
        "--refinement-plan",
        type=Path,
        help="Import an upstream robopad.proposed_evaluation_plan without regenerating its schedule.",
    )
    parser.add_argument(
        "--refinement-run-id",
        help="Run identity for an imported Refinement/Refresh plan.",
    )
    parser.add_argument(
        "--refinement-execution-protocol",
        type=Path,
        help="JSON frozen M/S/P execution envelope to bind to an imported source plan.",
    )
    parser.add_argument(
        "--outcome-plan",
        type=Path,
        help="Verify a RoboPAD smolvla_outcome_plan_v1 preflight artifact.",
    )
    parser.add_argument(
        "--verify-source-snapshot",
        type=Path,
        help="Verify a retained source-snapshot manifest against --source-root.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Local checkout used by --verify-source-snapshot.",
    )
    parser.add_argument(
        "--robochallenge-records",
        type=Path,
        help="Audit canonical RoboChallenge observation/action JSONL records.",
    )
    parser.add_argument(
        "--robochallenge-output",
        type=Path,
        help="Write the RoboChallenge protocol audit report.",
    )
    parser.add_argument(
        "--smolvla-manifest",
        type=Path,
        help="Validate an archived external SmolVLA deployment manifest.",
    )
    parser.add_argument(
        "--smolvla-summary",
        type=Path,
        help="Summary JSON paired with --smolvla-manifest.",
    )
    parser.add_argument(
        "--smolvla-output",
        type=Path,
        help="Write the archived SmolVLA evidence report.",
    )
    parser.add_argument(
        "--smolvla-manifest-sha256",
        help="Require the archived SmolVLA manifest to match this independent digest.",
    )
    parser.add_argument(
        "--smolvla-summary-sha256",
        help="Require the archived SmolVLA summary to match this independent digest.",
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
    artifact_group = parser.add_mutually_exclusive_group()
    artifact_group.add_argument(
        "--artifact-store",
        type=Path,
        help="Publish the executed campaign bundle to a local content-addressed store.",
    )
    artifact_group.add_argument(
        "--artifact-url",
        help="Publish the executed campaign bundle to a digest-addressed HTTP object store.",
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
    parser.add_argument(
        "--verify-artifact",
        type=Path,
        help="Verify an existing run artifact directory without executing it.",
    )
    parser.add_argument(
        "--verify-archive",
        type=Path,
        help="Verify a campaign ZIP without extracting it.",
    )
    parser.add_argument(
        "--trusted-archive-sha256",
        help="Require --verify-archive to match this independent archive digest.",
    )
    parser.add_argument(
        "--verify-scenario-archive",
        type=Path,
        help="Verify a scenario ZIP without extracting it.",
    )
    parser.add_argument(
        "--trusted-scenario-archive-sha256",
        help="Require --verify-scenario-archive to match an independent digest.",
    )
    parser.add_argument(
        "--fetch-artifact",
        metavar="SHA256",
        help="Fetch a content-addressed campaign archive from --artifact-store or --artifact-url.",
    )
    parser.add_argument(
        "--extract-output",
        type=Path,
        help="Destination for --fetch-artifact extraction.",
    )
    parser.add_argument(
        "--audit-output",
        type=Path,
        help="Audit an existing campaign directory without executing adapters.",
    )
    parser.add_argument(
        "--acceptance-output",
        type=Path,
        help="Write the executable scientific acceptance-contract report.",
    )
    parser.add_argument(
        "--acceptance-evidence",
        type=Path,
        help=(
            "JSON mapping of explicit external acceptance evidence, such as "
            "policy_transparent or recovery_verified."
        ),
    )
    parser.add_argument("--policy-parity-report", type=Path)
    parser.add_argument("--recovery-report", type=Path)
    parser.add_argument("--statistics-report", type=Path)
    parser.add_argument("--reproducibility-report", type=Path)
    parser.add_argument(
        "--transfer-records",
        type=Path,
        help="JSON/JSONL matched simulation/physical records for transfer analysis.",
    )
    parser.add_argument(
        "--transfer-output",
        type=Path,
        help="Write the serialized transfer-fidelity report.",
    )
    parser.add_argument("--recovery-records", type=Path)
    parser.add_argument("--recovery-output", type=Path)
    parser.add_argument("--recovery-plan", type=Path)
    parser.add_argument(
        "--counterfactual-interventions",
        type=Path,
        help="JSON array of frozen robustness interventions to bind to --frozen-plan.",
    )
    parser.add_argument(
        "--counterfactual-output",
        type=Path,
        help="Write a serialized counterfactual plan.",
    )
    parser.add_argument(
        "--validate-search-plan",
        type=Path,
        help="Load and validate a serialized counterexample-search plan.",
    )
    parser.add_argument(
        "--validate-confirmation-plan",
        type=Path,
        help="Load and validate a serialized independent confirmation plan.",
    )
    parser.add_argument(
        "--search-results",
        type=Path,
        help="Audit serialized counterexample-search results against --search-plan.",
    )
    parser.add_argument(
        "--search-plan",
        type=Path,
        help="Frozen search plan required by --search-results.",
    )
    parser.add_argument(
        "--confirmation-results",
        type=Path,
        help="Audit serialized confirmation results against --confirmation-plan.",
    )
    parser.add_argument(
        "--confirmation-plan",
        type=Path,
        help="Frozen confirmation plan required by --confirmation-results.",
    )
    parser.add_argument(
        "--claim-type",
        choices=[claim.value for claim in ClaimType],
        default=ClaimType.SINGLE_RUN_OUTCOME.value,
        help="Claim contract to apply when auditing an existing campaign.",
    )
    parser.add_argument(
        "--compare-campaign",
        acti