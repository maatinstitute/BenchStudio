import json

from benchstudio.campaigns import LocalArtifactStore, load_campaign_document
from benchstudio.cli import main


def test_cli_compiles_campaign_spec(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "campaign.json"
    plan_path = tmp_path / "plan.json"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "cli-run"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["benchstudio-run", "--campaign-spec", str(spec_path), "--plan-output", str(plan_path)],
    )
    assert main() == 0
    assert json.loads(plan_path.read_text(encoding="utf-8"))["run_id"] == "cli-run"
    assert "compiled_plan=" in capsys.readouterr().out


def test_cli_validates_serialized_search_plan(monkeypatch, tmp_path, capsys):
    from benchstudio.campaigns import PerturbationDimension, compile_search_plan

    path = tmp_path / "search-plan.json"
    compile_search_plan(
        run_id="search",
        scenario_id="task",
        base_condition_id="base",
        dimensions=(PerturbationDimension("x", (0, 1)),),
        seeds=[1],
    ).write(path)
    monkeypatch.setattr("sys.argv", ["benchstudio-run", "--validate-search-plan", str(path)])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True
    assert report["case_count"] == 2


def test_cli_validates_serialized_confirmation_plan(monkeypatch, tmp_path, capsys):
    from benchstudio.campaigns import SearchCandidate, compile_confirmation_plan

    path = tmp_path / "confirmation-plan.json"
    compile_confirmation_plan(
        run_id="confirmation",
        source_search_digest_sha256="a" * 64,
        candidates=[SearchCandidate("candidate", "task", "state", "search", 1, "b" * 64)],
        confirmation_seeds=[2],
    ).write(path)
    monkeypatch.setattr("sys.argv", ["benchstudio-run", "--validate-confirmation-plan", str(path)])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is True
    assert report["case_count"] == 1


def test_campaign_document_loader_rejects_non_mapping_json(tmp_path):
    path = tmp_path / "campaign.json"
    path.write_text("[]", encoding="utf-8")
    import pytest

    with pytest.raises(ValueError, match="top-level mapping"):
        load_campaign_document(path)


def test_cli_reports_adapter_readiness(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["benchstudio-run", "--readiness"])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert {item["simulator_id"] for item in report["simulators"]} >= {"mock", "mujoco"}
    assert {item["adapter_id"] for item in report["models"]} >= {"mock"}


def test_cli_compares_frozen_campaign_directories(monkeypatch, tmp_path, capsys):
    from benchstudio.campaigns import CampaignExecutor, CampaignPlanner
    from benchstudio.mock import MockPolicy, MockSimulator

    plan = CampaignPlanner(
        run_id="compare-cli", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    left = tmp_path / "left"
    right = tmp_path / "right"
    for output in (left, right):
        CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    output = tmp_path / "comparison.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--compare-campaign",
            f"left={left}",
            "--compare-campaign",
            f"right={right}",
            "--comparison-scenario-id",
            "task",
            "--comparison-output",
            str(output),
        ],
    )
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["divergence"]["left_vs_right"]["compared_episodes"] == 1
    assert json.loads(capsys.readouterr().out)["schema"] == "benchstudio_comparison_report_v1"


def test_cli_writes_transfer_fidelity_report(monkeypatch, tmp_path):
    records = tmp_path / "transfer.jsonl"
    records.write_text(
        json.dumps(
            {
                "system_id": "policy-a",
                "pair_id": "pair-1",
                "simulation_success": True,
                "physical_success": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "transfer-report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--transfer-records",
            str(records),
            "--transfer-output",
            str(output),
        ],
    )
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema"] == "benchstudio_transfer_fidelity_report_v1"
    assert report["success_gap_physical_minus_simulation"] == -1.0


def test_cli_writes_recovery_report(monkeypatch, tmp_path):
    records = tmp_path / "recovery.jsonl"
    records.write_text(
        "\n".join(
            [
                json.dumps({"pair_id": "p1", "branch": "nominal", "success": False}),
                json.dumps(
                    {
                        "pair_id": "p1",
                        "branch": "intervention",
                        "success": True,
                        "recovery_time_ms": 10,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "recovery-report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--recovery-records",
            str(records),
            "--recovery-output",
            str(output),
        ],
    )
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema"] == "benchstudio_recovery_report_v1"
    assert report["recovery_rate"] == 1.0


def test_acceptance_evidence_rejects_invalid_recovery_lineage(tmp_path):
    from benchstudio.cli import _load_report_acceptance_evidence

    path = tmp_path / "recovery-report.json"
    path.write_text(
        json.dumps(
            {
                "schema": "benchstudio_recovery_report_v1",
                "lineage_valid": False,
                "issues": [],
                "matched_pairs": 3,
            }
        ),
        encoding="utf-8",
    )
    assert _load_report_acceptance_evidence(None, path, None, None) == {"recovery_verified": False}


def test_acceptance_evidence_rejects_schema_less_impersonation(tmp_path):
    from benchstudio.cli import _load_report_acceptance_evidence

    recovery = tmp_path / "recovery.json"
    recovery.write_text(
        json.dumps({"issues": [], "matched_pairs": 3, "lineage_valid": True}),
        encoding="utf-8",
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"equivalent": True}), encoding="utf-8")
    assert _load_report_acceptance_evidence(policy, recovery, None, None) == {
        "policy_transparent": False,
        "recovery_verified": False,
    }


def test_cli_validates_recovery_report_against_frozen_counterfactual_plan(monkeypatch, tmp_path):
    from benchstudio.campaigns import (
        CampaignPlanner,
        CounterfactualEvaluation,
        Intervention,
        compile_counterfactual_plan,
        execute_counterfactual_plan,
    )

    plan = compile_counterfactual_plan(
        CampaignPlanner(
            run_id="cli-cf", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
        ).freeze(),
        [Intervention("delay", 1, "sensor_delay", {"ms": 10})],
    )
    evidence_dir = tmp_path / "evidence"
    execute_counterfactual_plan(
        plan,
        lambda cell: CounterfactualEvaluation(success=cell.branch == "nominal"),
        output=evidence_dir,
    )
    plan_path = tmp_path / "counterfactual-plan.json"
    plan.write(plan_path)
    output = tmp_path / "recovery-report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--recovery-records",
            str(evidence_dir / "counterfactual-results.jsonl"),
            "--recovery-plan",
            str(plan_path),
            "--recovery-output",
            str(output),
        ],
    )
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["lineage_valid"] is True
    assert report["lineage_issues"] == []


def test_cli_compares_frozen_policy_traces(monkeypatch, tmp_path, capsys):
    from benchstudio.integrations import POLICY_TRACE_SCHEMA

    reference = tmp_path / "reference.jsonl"
    instrumented = tmp_path / "instrumented.jsonl"
    row = {"schema": POLICY_TRACE_SCHEMA, "sequence": 0, "actions": [1], "metadata": {}}
    reference.write_text(json.dumps(row) + "\n", encoding="utf-8")
    instrumented.write_text(json.dumps(row) + "\n", encoding="utf-8")
    output = tmp_path / "parity.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--compare-policy-traces",
            str(reference),
            str(instrumented),
            "--parity-output",
            str(output),
        ],
    )
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["policy"]["equivalent"] is True
    assert json.loads(capsys.readouterr().out)["schema"] == "benchstudio_parity_report_v1"


def test_cli_verifies_existing_artifact_without_execution(monkeypatch, tmp_path, capsys):
    from benchstudio.evidence import sha256_file
    from benchstudio.mock import MockPolicy, MockSimulator
    from benchstudio.runner import RunConfig, run_episodes

    run_dir = tmp_path / "run"
    run_episodes(MockPolicy(), MockSimulator(), RunConfig(), run_dir)
    digest = sha256_file(run_dir / "artifact-manifest.json")
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--verify-artifact",
            str(run_dir),
            "--trusted-manifest-sha256",
            digest,
        ],
    )
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is True
    assert result["trust_anchor"]["external_reference_supplied"] is True


def test_cli_verifies_campaign_archive_without_extraction(monkeypatch, tmp_path, capsys):
    from benchstudio.campaigns import CampaignExecutor, CampaignPlanner, build_campaign_archive
    from benchstudio.mock import MockPolicy, MockSimulator

    plan = CampaignPlanner(
        run_id="archive-cli", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    campaign = tmp_path / "campaign"
    CampaignExecutor(plan, campaign, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    archive = tmp_path / "campaign.zip"
    archive.write_bytes(build_campaign_archive(campaign))
    monkeypatch.setattr("sys.argv", ["benchstudio-run", "--verify-archive", str(archive)])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "benchstudio_campaign_archive_verification_v1"
    assert result["valid"] is True


def test_cli_fetches_and_extracts_local_artifact(monkeypatch, tmp_path, capsys):
    from benchstudio.campaigns import (
        CampaignExecutor,
        CampaignPlanner,
        LocalArtifactStore,
        publish_campaign_archive,
    )
    from benchstudio.mock import MockPolicy, MockSimulator

    plan = CampaignPlanner(
        run_id="fetch-cli", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    campaign = tmp_path / "campaign"
    CampaignExecutor(plan, campaign, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    store_path = tmp_path / "store"
    reference = publish_campaign_archive(campaign, LocalArtifactStore(store_path))
    destination = tmp_path / "extracted"
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--fetch-artifact",
            reference.digest_sha256,
            "--artifact-store",
            str(store_path),
            "--extract-output",
            str(destination),
        ],
    )
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["digest_sha256"] == reference.digest_sha256
    assert (destination / "campaign-plan.json").is_file()


def test_cli_returns_nonzero_for_invalid_artifact(monkeypatch, tmp_path, capsys):
    run_dir = tmp_path / "missing"
    monkeypatch.setattr("sys.argv", ["benchstudio-run", "--verify-artifact", str(run_dir)])
    assert main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False


def test_cli_audits_existing_campaign_without_execution(monkeypatch, tmp_path, capsys):
    from benchstudio.campaigns import CampaignExecutor, CampaignPlanner
    from benchstudio.mock import MockPolicy, MockSimulator

    plan = CampaignPlanner(
        run_id="audit-cli", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    monkeypatch.setattr("sys.argv", ["benchstudio-run", "--audit-output", str(output)])
    assert main() == 0
    audit = json.loads(capsys.readouterr().out)
    assert audit["attempts_complete"] is True
    assert audit["evidence_verified"] is True


def test_cli_writes_fail_closed_acceptance_report(monkeypatch, tmp_path, capsys):
    from benchstudio.campaigns import CampaignExecutor, CampaignPlanner
    from benchstudio.mock import MockPolicy, MockSimulator

    plan = CampaignPlanner(
        run_id="acceptance-cli", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    campaign = tmp_path / "campaign"
    CampaignExecutor(plan, campaign, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    evidence = tmp_path / "acceptance-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "policy_transparent": True,
                "reproducible": True,
                "recovery_verified": True,
                "statistical_validity": True,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "acceptance.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--audit-output",
            str(campaign),
            "--acceptance-output",
            str(output),
            "--acceptance-evidence",
            str(evidence),
        ],
    )
    assert main() == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema"] == "benchstudio_evaluation_acceptance_v1"
    assert report["passed"] is False
    assert any(not check["passed"] for check in report["checks"])


def test_cli_campaign_audit_reopens_persisted_outcomes(monkeypatch, tmp_path, capsys):
    from benchstudio.analysis import OutcomeRecord
    from benchstudio.campaigns import CampaignExecutor, CampaignPlanner
    from benchstudio.mock import MockPolicy, MockSimulator

    plan = CampaignPlanner(
        run_id="audit-outcomes", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    executor = CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator())
    executor.run()
    executor.outcome_ledger().append(
        OutcomeRecord(
            plan.attempts[0].key.attempt_id,
            True,
            "declared",
            evaluator_id="mock-scorer",
            evaluator_revision="v1",
            authoritative=True,
        )
    )
    monkeypatch.setattr("sys.argv", ["benchstudio-run", "--audit-output", str(output)])
    assert main() == 0
    audit = json.loads(capsys.readouterr().out)
    assert audit["outcome_provenance"]["authoritative_records"] == 1
    assert audit["claim"]["prerequisites"]["authoritative_scorer_declared"] is True


def test_cli_verifies_detached_manifest_signature(monkeypatch, tmp_path, capsys):
    from benchstudio.evidence_signing import generate_ed25519_keypair, sign_manifest
    from benchstudio.mock import MockPolicy, MockSimulator
    from benchstudio.runner import RunConfig, run_episodes

    run_dir = tmp_path / "signed-run"
    run_episodes(MockPolicy(), MockSimulator(), RunConfig(), run_dir)
    private_key, public_key = generate_ed25519_keypair()
    signature_path = tmp_path / "manifest.sig"
    public_key_path = tmp_path / "manifest.pub"
    sign_manifest(run_dir / "artifact-manifest.json", private_key, signature_path)
    public_key_path.write_bytes(public_key)
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--verify-artifact",
            str(run_dir),
            "--manifest-signature",
            str(signature_path),
            "--trusted-public-key",
            str(public_key_path),
        ],
    )
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["signature"]["valid"] is True


def test_cli_executes_declared_registry_adapters(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "registry-campaign.json"
    output = tmp_path / "run"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "registry-cli"},
                "model": {"adapter": "mock"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator", "adapter": "mock"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--campaign-spec",
            str(spec_path),
            "--output",
            str(output),
            "--execute-registry",
        ],
    )
    assert main() == 0
    assert (output / "attempt-results.jsonl").is_file()
    assert "campaign_status=completed" in capsys.readouterr().out


def test_cli_executes_a_frozen_campaign_with_multiple_workers(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "parallel-campaign.json"
    output = tmp_path / "parallel-run"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "parallel-cli"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1, 2, 3, 4],
                    "paired": True,
                    "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--campaign-spec",
            str(spec_path),
            "--output",
            str(output),
            "--execute-mock",
            "--workers",
            "2",
        ],
    )
    assert main() == 0
    assert len((output / "attempt-results.jsonl").read_text().splitlines()) == 4
    assert "missing=0" in capsys.readouterr().out


def test_cli_rejects_non_positive_worker_count(monkeypatch, tmp_path):
    spec_path = tmp_path / "campaign.json"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "invalid-workers"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["benchstudio-run", "--campaign-spec", str(spec_path), "--workers", "0"],
    )
    with __import__("pytest").raises(SystemExit):
        main()


def test_cli_can_execute_compiled_campaign_with_mock_backend(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "campaign.json"
    plan_path = tmp_path / "plan.json"
    output = tmp_path / "run"
    archive = tmp_path / "campaign.zip"
    artifact_store = tmp_path / "artifact-store"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "cli-execute"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--campaign-spec",
            str(spec_path),
            "--plan-output",
            str(plan_path),
            "--output",
            str(output),
            "--execute-mock",
            "--audit",
            "--archive-output",
            str(archive),
            "--artifact-store",
            str(artifact_store),
        ],
    )
    assert main() == 0
    assert (output / "attempt-results.jsonl").is_file()
    assert archive.is_file()
    assert list(artifact_store.rglob("*.zip"))
    captured = capsys.readouterr()
    assert "campaign_status=completed" in captured.out
    assert "audit_status=qualified" in captured.out
    assert "artifact_sha256=" in captured.out


def test_cli_can_select_http_artifact_publication(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "campaign.json"
    output = tmp_path / "run"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "http-artifact"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
                },
            }
        ),
        encoding="utf-8",
    )
    seen = {}

    class FakeHttpStore:
        def __init__(self, url):
            seen["url"] = url
            self._local = LocalArtifactStore(tmp_path / "http-store")

        def publish_archive(self, archive, *, digest_sha256):
            return self._local.publish_archive(archive, digest_sha256=digest_sha256)

    monkeypatch.setattr("benchstudio.cli.HttpArtifactStore", FakeHttpStore)
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--campaign-spec",
            str(spec_path),
            "--output",
            str(output),
            "--execute-mock",
            "--artifact-url",
            "https://objects.example.test/benchstudio",
        ],
    )
    assert main() == 0
    assert seen["url"] == "https://objects.example.test/benchstudio"
    assert "artifact_uri=" in capsys.readouterr().out
