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
    LocalArtifactStore,
    compile_campaign_spec,
    load_campaign_document,
    retrieve_campaign_archive,
    verify_campaign_archive,
)
from .compare import build_campaign_comparison_report
from .evidence import verify_artifact_manifest
from .mock import MockPolicy, MockSimulator
from .model_adapters import default_model_registry
from .runner import RunConfig, run_episodes
from .scenarios import verify_scenario_archive


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
        action="append",
        metavar="BACKEND=PATH",
        help="Compare frozen campaign directories; repeat once per backend.",
    )
    parser.add_argument(
        "--comparison-scenario-id",
        help="Scenario identifier for --compare-campaign.",
    )
    parser.add_argument(
        "--comparison-output",
        type=Path,
        help="Write the JSON comparison report to this path.",
    )
    parser.add_argument(
        "--transfer-backends",
        metavar="SIMULATION=PHYSICAL",
        help="Add transfer-fidelity analysis for two named --compare-campaign backends.",
    )
    parser.add_argument(
        "--compare-policy-traces",
        nargs=2,
        metavar=("REFERENCE", "INSTRUMENTED"),
        help="Compare two frozen benchstudio.policy_trace.v1 JSONL files.",
    )
    parser.add_argument(
        "--parity-output",
        type=Path,
        help="Write the policy-trace parity evidence to this path.",
    )
    parser.add_argument(
        "--trusted-manifest-sha256",
        help="Require --verify-artifact to match this independently supplied manifest digest.",
    )
    parser.add_argument(
        "--manifest-signature",
        type=Path,
        help="Detached manifest signature to verify with --trusted-public-key.",
    )
    parser.add_argument(
        "--trusted-public-key",
        type=Path,
        help="PEM public key used to verify --manifest-signature.",
    )
    args = parser.parse_args()
    if args.verify_archive is not None:
        result = verify_campaign_archive(
            args.verify_archive.read_bytes(), expected_sha256=args.trusted_archive_sha256
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["valid"] else 2
    if args.trusted_archive_sha256 is not None:
        parser.error("--trusted-archive-sha256 requires --verify-archive")
    if args.verify_scenario_archive is not None:
        result = verify_scenario_archive(
            args.verify_scenario_archive.read_bytes(),
            expected_sha256=args.trusted_scenario_archive_sha256,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["valid"] else 2
    if args.trusted_scenario_archive_sha256 is not None:
        parser.error("--trusted-scenario-archive-sha256 requires --verify-scenario-archive")
    if args.fetch_artifact is not None:
        if args.extract_output is None:
            parser.error("--fetch-artifact requires --extract-output")
        if args.artifact_store is not None:
            store = LocalArtifactStore(args.artifact_store)
        elif args.artifact_url is not None:
            store = HttpArtifactStore(args.artifact_url)
        else:
            parser.error("--fetch-artifact requires --artifact-store or --artifact-url")
        digest = retrieve_campaign_archive(store, args.fetch_artifact, args.extract_output)
        print(json.dumps({"digest_sha256": digest, "extracted_to": str(args.extract_output)}))
        return 0
    if args.extract_output is not None:
        parser.error("--extract-output requires --fetch-artifact")
    if args.validate_search_plan is not None and args.validate_confirmation_plan is not None:
        parser.error("plan validation options are mutually exclusive")
    if args.validate_search_plan is not None:
        from .campaigns import load_search_plan

        plan = load_search_plan(args.validate_search_plan)
        payload = {
            "schema": "benchstudio.counterexample_search_validation_v1",
            "run_id": plan.run_id,
            "scenario_id": plan.scenario_id,
            "case_count": len(plan.cases),
            "plan_digest_sha256": plan.plan_digest_sha256,
            "valid": True,
        }
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.validate_confirmation_plan is not None:
        from .campaigns import load_confirmation_plan

        plan = load_confirmation_plan(args.validate_confirmation_plan)
        payload = {
            "schema": "benchstudio.confirmation_validation_v1",
            "run_id": plan.run_id,
            "case_count": len(plan.cases),
            "source_search_digest_sha256": plan.source_search_digest_sha256,
            "plan_digest_sha256": plan.plan_digest_sha256,
            "valid": True,
        }
        print(json.dumps(payload, sort_keys=True))
        return 0
    result_audit_options = (
        args.search_results is not None,
        args.search_plan is not None,
        args.confirmation_results is not None,
        args.confirmation_plan is not None,
    )
    if any(result_audit_options):
        if args.search_results is not None or args.search_plan is not None:
            if args.search_results is None or args.search_plan is None:
                parser.error("--search-results and --search-plan must be supplied together")
            if args.confirmation_results is not None or args.confirmation_plan is not None:
                parser.error("search and confirmation result audits are mutually exclusive")
            from .campaigns import audit_search_results, load_search_plan, load_search_results

            plan = load_search_plan(args.search_plan)
            records = load_search_results(args.search_results)
            audit = audit_search_results(plan, records)
            payload = {
                "schema": "benchstudio.counterexample_search_audit_v1",
                "plan_digest_sha256": plan.plan_digest_sha256,
                "result_path": str(args.search_results),
                **audit.to_dict(),
            }
        else:
            if args.confirmation_results is None or args.confirmation_plan is None:
                parser.error(
                    "--confirmation-results and --confirmation-plan must be supplied together"
                )
            from .campaigns import (
                audit_confirmation_results,
                load_confirmation_plan,
                load_confirmation_results,
            )

            plan = load_confirmation_plan(args.confirmation_plan)
            records = load_confirmation_results(args.confirmation_results)
            audit = audit_confirmation_results(plan, records)
            payload = {
                "schema": "benchstudio.confirmation_audit_v1",
                "plan_digest_sha256": plan.plan_digest_sha256,
                "result_path": str(args.confirmation_results),
                **audit.to_dict(),
            }
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload["complete"] else 2
    if args.compare_policy_traces is not None:
        reference, instrumented = map(Path, args.compare_policy_traces)
        report = compare_policy_trace_files(reference, instrumented)
        payload = {
            "schema": "benchstudio_parity_report_v1",
            "metadata": {
                "reference_trace": str(reference),
                "instrumented_trace": str(instrumented),
            },
            "policy": report.to_dict(),
        }
        if args.parity_output is not None:
            args.parity_output.parent.mkdir(parents=True, exist_ok=True)
            args.parity_output.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        print(json.dumps(payload, sort_keys=True))
        return 0 if report.equivalent else 2
    if args.transfer_records is not None:
        report = summarize_transfer_fidelity(load_transfer_records(args.transfer_records))
        if args.transfer_output is not None:
            write_transfer_fidelity_report(report, args.transfer_output)
        print(json.dumps(report.to_dict(), sort_keys=True))
        return 0 if report.complete_pairs > 0 and not report.issues else 2
    if args.recovery_records is not None:
        report = summarize_recovery_outcomes(load_recovery_records(args.recovery_records))
        if args.recovery_plan is not None:
            from .analysis import audit_counterfactual_outcomes
            from .campaigns import load_counterfactual_plan

            records = load_recovery_records(args.recovery_records)
            lineage = audit_counterfactual_outcomes(
                load_counterfactual_plan(args.recovery_plan), records
            )
            report = replace(
                report,
                lineage_valid=lineage.complete,
                lineage_issues=(
                    tuple(lineage.missing_branch_attempt_ids)
                    + tuple(lineage.unknown_branch_attempt_ids)
                    + tuple(lineage.duplicate_branch_attempt_ids)
                    + tuple(lineage.lineage_issues)
                ),
            )
        if args.recovery_output is not None:
            write_recovery_report(report, args.recovery_output)
        print(json.dumps(report.to_dict(), sort_keys=True))
        return (
            0
            if report.matched_pairs > 0 and not report.issues and report.lineage_valid is not False
            else 2
        )
    if args.compare_campaign is not None:
        if not args.comparison_scenario_id:
            parser.error("--compare-campaign requires --comparison-scenario-id")
        backend_campaigns: dict[str, Path] = {}
        for value in args.compare_campaign:
            backend, separator, path = value.partition("=")
            if not separator or not backend or not path:
                parser.error("--compare-campaign values must use BACKEND=PATH")
            if backend in backend_campaigns:
                parser.error(f"duplicate comparison backend: {backend}")
            backend_campaigns[backend] = Path(path)
        transfer_backends = None
        if args.transfer_backends is not None:
            simulation, separator, physical = args.transfer_backends.partition("=")
            if not separator or not simulation or not physical:
                parser.error("--transfer-backends must use SIMULATION=PHYSICAL")
            transfer_backends = (simulation, physical)
        report = build_campaign_comparison_report(
            scenario_id=args.comparison_scenario_id,
            backend_campaigns=backend_campaigns,
            transfer_backends=transfer_backends,
        )
        if args.comparison_output is not None:
            args.comparison_output.parent.mkdir(parents=True, exist_ok=True)
            args.comparison_output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        print(json.dumps(report, sort_keys=True))
        return 0 if not report["errors"] else 2
    if args.verify_artifact is None and any(
        value is not None
        for value in (
            args.trusted_manifest_sha256,
            args.manifest_signature,
            args.trusted_public_key,
        )
    ):
        parser.error("artifact trust options require --verify-artifact")
    if args.verify_artifact is not None:
        public_key = (
            args.trusted_public_key.read_bytes() if args.trusted_public_key is not None else None
        )
        result = verify_artifact_manifest(
            args.verify_artifact,
            trusted_manifest_sha256=args.trusted_manifest_sha256,
            signature_path=args.manifest_signature,
            trusted_public_key=public_key,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["valid"] else 2
    if args.audit_output is not None:
        audit = audit_campaign_directory(args.audit_output, claim_type=ClaimType(args.claim_type))
        if args.acceptance_output is not None or any(
            value is not None
            for value in (
                args.acceptance_evidence,
                args.policy_parity_report,
                args.recovery_report,
                args.statistics_report,
                args.reproducibility_report,
            )
        ):
            evidence = _load_acceptance_evidence(args.acceptance_evidence)
            evidence.update(
                _load_report_acceptance_evidence(
                    args.policy_parity_report,
                    args.recovery_report,
                    args.statistics_report,
                    args.reproducibility_report,
                )
            )
            acceptance = audit_evaluation_acceptance(
                audit,
                policy_transparent=evidence.get("policy_transparent"),
                reproducible=evidence.get("reproducible"),
                recovery_verified=evidence.get("recovery_verified"),
                statistical_validity=evidence.get("statistical_validity"),
            )
            if args.acceptance_output is not None:
                args.acceptance_output.parent.mkdir(parents=True, exist_ok=True)
                args.acceptance_output.write_text(
                    json.dumps(acceptance.to_dict(), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            print(json.dumps(acceptance.to_dict(), sort_keys=True))
            return 0 if acceptance.passed else 2
        print(json.dumps(audit.to_dict(), sort_keys=True))
        return 0 if audit.attempts_complete and audit.evidence_verified else 2
    if args.readiness:
        simulator_registry = default_registry()
        model_registry = default_model_registry()
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
        print(
            json.dumps(
                {
                    "simulators": simulators,
                    "models": models,
                    "simulator_discovery": list(simulator_registry.discovery_diagnostics),
                    "model_discovery": list(model_registry.discovery_diagnostics),
                },
                sort_keys=True,
            )
        )
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
            campaign_status = (
                "failed"
                if summary.failed_attempt_ids or summary.missing_attempt_ids
                else "completed"
            )
            print(
                f"campaign_status={campaign_status} "
                f"committed={len(summary.committed_attempt_ids)} "
                f"failed={len(summary.failed_attempt_ids)} "
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
            artifact_store = None
            if args.artifact_store is not None:
                artifact_store = LocalArtifactStore(args.artifact_store)
            elif args.artifact_url is not None:
                artifact_store = HttpArtifactStore(args.artifact_url)
            if artifact_store is not None:
                reference = executor.publish_artifact(artifact_store)
                print(
                    f"artifact_uri={reference['uri']} artifact_sha256={reference['digest_sha256']} "
                    f"artifact_bytes={reference['bytes']}"
                )
            return 0 if campaign_status == "completed" else 2
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


def _load_acceptance_evidence(path: Path | None) -> dict[str, bool]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("acceptance evidence must be a JSON mapping")
    allowed = {
        "policy_transparent",
        "reproducible",
        "recovery_verified",
        "statistical_validity",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ValueError("unsupported acceptance evidence: " + ", ".join(sorted(unknown)))
    if any(not isinstance(item, bool) for item in value.values()):
        raise ValueError("acceptance evidence values must be booleans")
    return value


def _load_report_acceptance_evidence(
    policy_path: Path | None,
    recovery_path: Path | None,
    statistics_path: Path | None,
    reproducibility_path: Path | None,
) -> dict[str, bool]:
    evidence: dict[str, bool] = {}
    if policy_path is not None:
        payload = _load_json_mapping(policy_path)
        if payload.get("schema") not in {
            "benchstudio_parity_report_v1",
            "benchstudio_policy_parity_report_v1",
        }:
            payload = {}
        policy = payload.get("policy", payload)
        evidence["policy_transparent"] = bool(
            isinstance(policy, dict) and policy.get("equivalent") is True
        )
    if recovery_path is not None:
        payload = _load_json_mapping(recovery_path)
        evidence["recovery_verified"] = bool(
            payload.get("schema") == "benchstudio_recovery_report_v1"
            and payload.get("lineage_valid") is not False
            and (
                payload.get("complete") is True
                or payload.get("passed") is True
                or (payload.get("issues") == [] and payload.get("matched_pairs", 0) > 0)
            )
        )
    if statistics_path is not None:
        payload = _load_json_mapping(statistics_path)
        evidence["statistical_validity"] = bool(
            payload.get("schema") in {None, "benchstudio_paired_outcomes_v1"}
            and payload.get("matched_pairs", 0) > 0
            and payload.get("success_gap_confidence_interval") is not None
        )
    if reproducibility_path is not None:
        payload = _load_json_mapping(reproducibility_path)
        evidence["reproducible"] = bool(
            payload.get("reproducible") is True or payload.get("verified") is True
        )
    return evidence


def _load_json_mapping(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON mapping")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
