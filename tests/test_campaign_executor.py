from __future__ import annotations

import io
import json
import sys
import zipfile

import pytest

from benchstudio.adapters import default_registry
from benchstudio.analysis import (
    ClaimType,
    OutcomeRecord,
    TimingProvenance,
    audit_execution_overhead,
    write_execution_overhead,
)
from benchstudio.campaigns import (
    CampaignArchiveError,
    CampaignExecutor,
    CampaignPlanner,
    LocalArtifactStore,
    WorkerLeaseManager,
    build_campaign_archive,
    campaign_archive_digest,
    compile_campaign_spec,
    extract_verified_campaign_archive,
    verify_campaign_archive,
    write_campaign_archive,
)
from benchstudio.mock import MockPolicy, MockSimulator
from benchstudio.model_adapters import default_model_registry


def test_campaign_executor_uses_frozen_attempts_and_resumes_idempotently(tmp_path):
    plan = CampaignPlanner(
        run_id="run-1",
        scenario_id="mock-task",
        conditions=[{"denoising_steps": 2, "action_prefix": 1}],
        seeds=[7, 8],
    ).freeze()
    executor = CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
    )
    first = executor.run()
    assert first.committed_attempt_ids == ("attempt-000000", "attempt-000001")
    assert first.missing_attempt_ids == ()
    second = CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
    ).run()
    assert second.skipped_attempt_ids == first.committed_attempt_ids
    records = [
        json.loads(line)
        for line in (tmp_path / "campaign" / "attempt-results.jsonl").read_text().splitlines()
    ]
    assert len(records) == 2
    assert {record["pair_id"] for record in records} == {
        plan.attempts[0].key.pair_id,
        plan.attempts[1].key.pair_id,
    }


def test_campaign_executor_can_run_pending_attempts_with_multiple_workers(tmp_path):
    plan = CampaignPlanner(
        run_id="parallel-run",
        scenario_id="mock-task",
        conditions=[{"denoising_steps": 2, "action_prefix": 1}],
        seeds=[1, 2, 3, 4],
    ).freeze()
    result = CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
    ).run_parallel(2)
    assert result.committed_attempt_ids == tuple(
        attempt.key.attempt_id for attempt in plan.attempts
    )
    assert result.missing_attempt_ids == ()
    records = (tmp_path / "campaign" / "attempt-results.jsonl").read_text().splitlines()
    assert len(records) == len(plan.attempts)


def test_campaign_executor_can_run_an_explicit_frozen_attempt_batch(tmp_path):
    plan = CampaignPlanner(
        run_id="batch-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1, 2]
    ).freeze()
    output = tmp_path / "campaign"
    first = CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run(
        attempt_ids=["attempt-000000"]
    )
    assert first.committed_attempt_ids == ("attempt-000000",)
    assert first.missing_attempt_ids == ("attempt-000001",)
    second = CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run(
        attempt_ids=["attempt-000001"]
    )
    assert second.committed_attempt_ids == ("attempt-000001",)
    assert second.missing_attempt_ids == ()


def test_campaign_executor_rejects_attempts_outside_frozen_batch(tmp_path):
    plan = CampaignPlanner(
        run_id="batch-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    executor = CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
    )
    with pytest.raises(ValueError, match="outside the frozen plan"):
        executor.run(attempt_ids=["not-planned"])


def test_campaign_executor_commits_infrastructure_failure_and_does_not_retry(tmp_path):
    plan = CampaignPlanner(
        run_id="failure-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()

    def failing_simulator(_attempt):
        raise RuntimeError("simulator worker unavailable")

    executor = CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), failing_simulator
    )
    first = executor.run()
    assert first.committed_attempt_ids == ()
    assert first.failed_attempt_ids == ("attempt-000000",)
    assert first.missing_attempt_ids == ()

    second = CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), failing_simulator
    ).run()
    assert second.failed_attempt_ids == ()
    assert second.skipped_attempt_ids == ("attempt-000000",)
    record = json.loads((tmp_path / "campaign" / "attempt-results.jsonl").read_text().strip())
    assert record["status"] == "infrastructure_failure"


def test_campaign_executor_reports_runner_failure_status_as_failed_attempt(tmp_path):
    class BrokenPolicy(MockPolicy):
        def predict(self, observation, *, denoising_steps):
            raise RuntimeError("policy unavailable")

    plan = CampaignPlanner(
        run_id="policy-failure-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    executor = CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: BrokenPolicy(), lambda _: MockSimulator()
    )
    result = executor.run()
    assert result.committed_attempt_ids == ()
    assert result.failed_attempt_ids == ("attempt-000000",)
    assert result.missing_attempt_ids == ()
    assert executor.audit().attempts_complete is True


def test_campaign_executor_treats_cleanup_failure_as_final_failed_attempt(tmp_path):
    class CloseFailureSimulator(MockSimulator):
        def close(self):
            super().close()
            raise RuntimeError("cleanup unavailable")

    plan = CampaignPlanner(
        run_id="cleanup-failure-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    executor = CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: CloseFailureSimulator()
    )
    result = executor.run()
    assert result.committed_attempt_ids == ()
    assert result.failed_attempt_ids == ("attempt-000000",)
    assert result.missing_attempt_ids == ()
    audit = executor.audit()
    assert audit.attempts_complete is True
    assert audit.status_counts == {"failed_cleanup": 1}


def test_campaign_executor_rejects_a_different_plan_at_existing_output(tmp_path):
    first = CampaignPlanner(
        run_id="run-1", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    CampaignExecutor(
        first, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
    )
    second = CampaignPlanner(
        run_id="run-1", scenario_id="task", conditions=[{"x": 2}], seeds=[1]
    ).freeze()
    import pytest

    with pytest.raises(ValueError, match="campaign plan"):
        CampaignExecutor(
            second, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
        )


def test_campaign_executor_accounts_for_attempts_leased_by_another_worker(tmp_path):
    plan = CampaignPlanner(
        run_id="run-1", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    leases = WorkerLeaseManager(tmp_path / "leases")
    held = leases.acquire(plan.attempts[0].key.attempt_id, "worker-a")
    assert held is not None
    result = CampaignExecutor(
        plan,
        tmp_path / "campaign",
        lambda _: MockPolicy(),
        lambda _: MockSimulator(),
        worker_id="worker-b",
        lease_manager=leases,
    ).run()
    assert result.committed_attempt_ids == ()
    assert result.leased_out_attempt_ids == ("attempt-000000",)


def test_campaign_executor_records_declared_cancellation(tmp_path):
    plan = CampaignPlanner(
        run_id="run-1", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    result = CampaignExecutor(
        plan,
        tmp_path / "campaign",
        lambda _: MockPolicy(),
        lambda _: MockSimulator(),
        cancelled_attempts=["attempt-000000"],
    ).run()
    assert result.cancelled_attempt_ids == ("attempt-000000",)
    assert result.missing_attempt_ids == ()


def test_campaign_executor_refuses_tampered_resumed_attempt(tmp_path):
    plan = CampaignPlanner(
        run_id="run-1", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    trace = output / "attempts" / "attempt-000000" / "episodes.jsonl"
    trace.write_text(trace.read_text() + "tampered\n")
    with __import__("pytest").raises(RuntimeError, match="evidence verification"):
        CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run()


def test_campaign_executor_preserves_environment_identity_in_evidence(tmp_path):
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "paired-environments"},
            "task": {"task_id": "mock-task"},
            "environments": [
                {"id": "sim-a", "kind": "simulator"},
                {"id": "sim-b", "kind": "simulator", "enabled": True},
            ],
            "evaluation": {
                "seeds": [7],
                "paired": True,
                "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
            },
        }
    )
    output = tmp_path / "campaign"
    result = CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    assert result.missing_attempt_ids == ()
    environments = []
    for attempt in plan.attempts:
        manifest = json.loads(
            (output / "attempts" / attempt.key.attempt_id / "manifest.json").read_text()
        )
        environments.append(manifest["config"]["environment_id"])
    assert environments == ["sim-a", "sim-b"]


def test_campaign_executor_binds_runtime_receipt_to_frozen_attempt(tmp_path):
    plan = CampaignPlanner(
        run_id="receipt-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    CampaignExecutor(
        plan,
        output,
        lambda _: MockPolicy(),
        lambda _: MockSimulator(),
        worker_id="worker-a",
        lease_manager=WorkerLeaseManager(tmp_path / "leases"),
    ).run()
    receipt = json.loads(
        (output / "attempts" / "attempt-000000" / "runtime-receipt.json").read_text()
    )
    assert receipt["run_id"] == plan.run_id
    assert receipt["attempt_id"] == "attempt-000000"
    assert receipt["plan_digest_sha256"] == plan.plan_digest_sha256
    assert receipt["worker_id"] == "worker-a"


def test_campaign_executor_scopes_episode_ids_to_frozen_attempt(tmp_path):
    plan = CampaignPlanner(
        run_id="identity-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    summary = json.loads((output / "attempts" / "attempt-000000" / "summary.json").read_text())
    assert summary["episodes"][0]["episode_id"] == "attempt-000000-episode-0000"


def test_campaign_executor_persists_environment_calibration(tmp_path):
    calibration = {
        "revision": "cal-v1",
        "camera": "sha256:" + "1" * 64,
        "action_transform": "sha256:" + "2" * 64,
    }
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "calibrated"},
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator", "calibration": calibration}],
            "evaluation": {"seeds": [1], "paired": True, "conditions": [{"x": 1}]},
        }
    )
    CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
    ).run()
    manifest = json.loads(
        (tmp_path / "campaign" / "attempts" / "attempt-000000" / "manifest.json").read_text()
    )
    assert manifest["calibration"] == calibration
    assert manifest["calibration_digest_sha256"].startswith("sha256:")


def test_campaign_executor_persists_benchmark_validity(tmp_path):
    validity = {
        "task_definition_revision": "task-v1",
        "dataset_lineage_digest": "sha256:" + "1" * 64,
        "contamination_review": "clear",
        "excluded_attempt_ids": [],
        "early_termination_policy": "success_allowed",
        "metric_revision": "metric-v1",
        "metric_scope": "official",
        "metric_stability": "stable",
    }
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "validity-evidence"},
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "validity": validity,
                "conditions": [{"x": 1}],
            },
        }
    )
    CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
    ).run()
    manifest = json.loads(
        (tmp_path / "campaign" / "attempts" / "attempt-000000" / "manifest.json").read_text()
    )
    assert manifest["benchmark_validity"] == validity


def test_campaign_executor_persists_checkpoint_pinned_model_reference(tmp_path):
    checkpoint = "sha256:" + "a" * 64
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "checkpoint-evidence"},
            "model": {
                "adapter": "mock",
                "architecture": "mock-v1",
                "checkpoint": checkpoint,
                "robot_profile": "mock-arm",
                "adapter_config": {"private_path": "/should-not-be-copied"},
            },
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {"seeds": [1], "paired": True, "conditions": [{"x": 1}]},
        }
    )
    CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
    ).run()
    manifest = json.loads(
        (tmp_path / "campaign" / "attempts" / "attempt-000000" / "manifest.json").read_text()
    )
    assert manifest["model_reference"] == {
        "adapter": "mock",
        "architecture": "mock-v1",
        "checkpoint": checkpoint,
        "robot_profile": "mock-arm",
    }


def test_campaign_executor_wires_resource_sampler_per_attempt(tmp_path):
    plan = CampaignPlanner(
        run_id="resource-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()

    def sampler_factory(_attempt):
        samples = iter([{"inference_calls": 2}, {"inference_calls": 5}])
        return lambda: next(samples)

    output = tmp_path / "campaign"
    CampaignExecutor(
        plan,
        output,
        lambda _: MockPolicy(),
        lambda _: MockSimulator(),
        resource_sampler_factory=sampler_factory,
    ).run()
    summary = json.loads((output / "attempts" / "attempt-000000" / "summary.json").read_text())
    assert summary["episodes"][0]["resource_metrics"]["inference_calls"] == 3


def test_campaign_executor_exposes_frozen_plan_audit(tmp_path):
    plan = CampaignPlanner(
        run_id="audit-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    executor = CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
    )
    executor.run()
    audit = executor.audit(
        claim_type=ClaimType.SINGLE_RUN_OUTCOME,
        evidence={"authoritative_scorer_declared": True},
    )
    assert audit.attempts_complete is True
    assert audit.evidence_verified is True
    assert audit.claim.status == "supported"


def test_campaign_executor_includes_persisted_execution_overhead_in_audit(tmp_path):
    plan = CampaignPlanner(
        run_id="overhead-audit-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    executor = CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator())
    executor.run()
    report = audit_execution_overhead(
        [10.0],
        [11.0],
        deadline_ms=15.0,
        timing_provenance=TimingProvenance("host_monotonic", "start", "end"),
    )
    write_execution_overhead(report, output / "execution-overhead.json")
    audit = executor.audit(evidence={"authoritative_scorer_declared": True})
    assert audit.execution_overhead == report
    assert audit.to_dict()["execution_overhead_valid"] is True


def test_campaign_executor_audit_rechecks_runtime_evidence(tmp_path):
    plan = CampaignPlanner(
        run_id="audit-receipt-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    executor = CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator())
    executor.run()
    (output / "attempts" / "attempt-000000" / "runtime-receipt.json").unlink()
    audit = executor.audit(
        evidence={"authoritative_scorer_declared": True},
    )
    assert audit.evidence_verified is False
    assert "runtime-receipt.json" in " ".join(audit.evidence_issues)


def test_campaign_executor_audit_reads_persisted_authoritative_outcomes(tmp_path):
    plan = CampaignPlanner(
        run_id="outcome-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    executor = CampaignExecutor(
        plan, tmp_path / "campaign", lambda _: MockPolicy(), lambda _: MockSimulator()
    )
    executor.run()
    executor.outcome_ledger().append(
        OutcomeRecord(
            plan.attempts[0].key.attempt_id,
            True,
            "official",
            "scorer",
            "rev-1",
            authoritative=True,
        )
    )
    audit = executor.audit()
    assert audit.outcome_provenance is not None
    assert audit.claim.status == "supported"


def test_campaign_executor_rejects_unsatisfied_frozen_backend_requirement(tmp_path):
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "backend-gated"},
            "task": {"task_id": "task"},
            "environments": [
                {
                    "id": "sim",
                    "kind": "simulator",
                    "adapter": "mock",
                    "required_capabilities": {"owns_physics": True},
                }
            ],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"x": 1}],
            },
        }
    )
    with pytest.raises(ValueError, match="backend requirements"):
        CampaignExecutor(
            plan,
            tmp_path / "campaign",
            lambda _: MockPolicy(),
            lambda _: MockSimulator(),
            adapter_registry=default_registry(discover_external=False),
        )


def test_campaign_executor_can_instantiate_declared_adapter(tmp_path):
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "registry-backed"},
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator", "adapter": "mock"}],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
            },
        }
    )
    result = CampaignExecutor(
        plan,
        tmp_path / "campaign",
        lambda _: MockPolicy(),
        adapter_registry=default_registry(discover_external=False),
    ).run()
    assert result.missing_attempt_ids == ()
    manifest = json.loads(
        (tmp_path / "campaign" / "attempts" / "attempt-000000" / "manifest.json").read_text()
    )
    assert manifest["simulator_id"] == "mock_simulator"


def test_campaign_executor_can_instantiate_declared_model_adapter(tmp_path):
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "model-registry-backed"},
            "model": {"adapter": "mock"},
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
            },
        }
    )
    result = CampaignExecutor(
        plan,
        tmp_path / "campaign",
        model_registry=default_model_registry(discover_external=False),
        simulator_factory=lambda _: MockSimulator(),
    ).run()
    assert result.missing_attempt_ids == ()


def test_campaign_executor_can_run_external_command_model_adapter(tmp_path):
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "external-model"},
            "model": {
                "adapter": "external_command",
                "adapter_config": {
                    "command": [
                        sys.executable,
                        "-c",
                        "import json,sys; json.load(sys.stdin); "
                        "print(json.dumps({'actions':[1,1]}))",
                    ]
                },
            },
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
            },
        }
    )
    result = CampaignExecutor(
        plan,
        tmp_path / "campaign",
        model_registry=default_model_registry(discover_external=False),
        simulator_factory=lambda _: MockSimulator(),
    ).run()
    assert result.missing_attempt_ids == ()


def test_campaign_executor_can_run_external_command_simulator_adapter(tmp_path):
    simulator_script = (
        "import json,sys; step=0;\n"
        "for line in sys.stdin:\n"
        " request=json.loads(line); op=request['operation'];\n"
        " if op=='reset': step=0;\n"
        " if op=='step': step+=1;\n"
        " if op=='close': break;\n"
        " print(json.dumps({'observation':{'sequence':step,'sim_time_s':step/10,'payload':{}},"
        "'done':step>=1,'success':step>=1}), flush=True)\n"
    )
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "external-simulator"},
            "task": {"task_id": "task"},
            "environments": [
                {
                    "id": "sim",
                    "kind": "simulator",
                    "adapter": "external_command",
                    "adapter_config": {"command": [sys.executable, "-u", "-c", simulator_script]},
                }
            ],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
            },
        }
    )
    result = CampaignExecutor(
        plan,
        tmp_path / "campaign",
        policy_factory=lambda _: MockPolicy(),
        adapter_registry=default_registry(discover_external=False),
    ).run()
    assert result.missing_attempt_ids == ()


def test_registry_backed_manifest_records_model_capabilities(tmp_path):
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "capability-evidence"},
            "model": {"adapter": "mock"},
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"x": 1}],
            },
        }
    )
    CampaignExecutor(
        plan,
        tmp_path / "campaign",
        model_registry=default_model_registry(discover_external=False),
        simulator_factory=lambda _: MockSimulator(),
    ).run()
    manifest = json.loads(
        (tmp_path / "campaign" / "attempts" / "attempt-000000" / "manifest.json").read_text()
    )
    assert manifest["model_adapter_id"] == "mock"
    assert manifest["model_capabilities"]["supports_cached_predictions"] is True


def test_expired_worker_lease_is_reclaimed_by_next_worker(tmp_path):
    now = [1_000_000_000]

    def clock():
        return now[0]

    leases = WorkerLeaseManager(tmp_path / "leases", lease_seconds=1, clock_ns=clock)
    first = leases.acquire("attempt-1", "worker-a")
    assert first is not None
    now[0] += 2_000_000_000
    second = leases.acquire("attempt-1", "worker-b")
    assert second is not None
    assert second.worker_id == "worker-b"


def test_worker_lease_renewal_remains_owner_bound(tmp_path):
    now = [1_000_000_000]

    def clock():
        return now[0]

    leases = WorkerLeaseManager(tmp_path / "leases", lease_seconds=1, clock_ns=clock)
    lease = leases.acquire("attempt-1", "worker-a")
    assert lease is not None
    renewed = leases.renew(lease)
    assert renewed.expires_at_ns > lease.expires_at_ns
    with __import__("pytest").raises(ValueError, match="owner"):
        leases.renew(type(lease)(lease.attempt_id, "worker-b", lease.expires_at_ns))


def test_campaign_archive_is_deterministic_and_extracts_verified_evidence(tmp_path):
    plan = CampaignPlanner(
        run_id="archive-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    first = build_campaign_archive(output)
    second = build_campaign_archive(output)
    assert first == second
    destination = tmp_path / "unpacked"
    digest = extract_verified_campaign_archive(
        first, destination, expected_sha256=campaign_archive_digest(first)
    )
    assert (destination / "campaign-plan.json").is_file()
    assert (destination / "attempt-results.jsonl").is_file()
    assert len(digest) == 64
    written = write_campaign_archive(output, tmp_path / "campaign.zip")
    assert written["sha256"] == campaign_archive_digest((tmp_path / "campaign.zip").read_bytes())
    with pytest.raises(CampaignArchiveError, match="already exists"):
        write_campaign_archive(output, tmp_path / "campaign.zip")


def test_campaign_executor_publishes_content_addressed_artifact(tmp_path):
    plan = CampaignPlanner(
        run_id="publish-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    executor = CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator())
    executor.run()
    reference = executor.publish_artifact(LocalArtifactStore(tmp_path / "store"))
    assert reference["schema"] == "benchstudio.campaign_archive.v1"
    assert len(reference["digest_sha256"]) == 64


def test_campaign_archive_rejects_symlinks_and_traversal(tmp_path):
    root = tmp_path / "campaign"
    root.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("outside")
    (root / "link").symlink_to(target)
    with pytest.raises(CampaignArchiveError, match="symlink"):
        build_campaign_archive(root)
    malicious = io.BytesIO()
    with zipfile.ZipFile(malicious, "w") as package:
        package.writestr("../escape.txt", "no")
    with pytest.raises(CampaignArchiveError, match="unsafe path"):
        extract_verified_campaign_archive(malicious.getvalue(), tmp_path / "unsafe")


def test_campaign_archive_can_be_verified_without_extraction(tmp_path):
    plan = CampaignPlanner(
        run_id="verify-archive", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    archive = build_campaign_archive(output)
    result = verify_campaign_archive(archive, expected_sha256=campaign_archive_digest(archive))
    assert result["valid"] is True
    tampered = verify_campaign_archive(
        archive + b"x", expected_sha256=campaign_archive_digest(archive)
    )
    assert tampered["valid"] is False


def test_campaign_archive_verifier_rejects_invalid_embedded_plan(tmp_path):
    root = tmp_path / "invalid-campaign"
    root.mkdir()
    (root / "campaign-plan.json").write_text("{}\n", encoding="utf-8")
    (root / "attempt-results.jsonl").write_text("\n", encoding="utf-8")
    result = verify_campaign_archive(build_campaign_archive(root))
    assert result["valid"] is False
    assert any(issue["reason"] == "invalid_campaign_plan" for issue in result["issues"])


def test_campaign_archive_verifier_rejects_invalid_ledger_status(tmp_path):
    plan = CampaignPlanner(
        run_id="invalid-status", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    ledger_path = output / "attempt-results.jsonl"
    record = json.loads(ledger_path.read_text(encoding="utf-8").strip())
    record["status"] = "not-a-final-status"
    ledger_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = verify_campaign_archive(build_campaign_archive(output))
    assert result["valid"] is False
    assert any(issue["reason"] == "ledger_status_invalid" for issue in result["issues"])


def test_campaign_archive_verifier_rejects_missing_evidence_flag(tmp_path):
    plan = CampaignPlanner(
        run_id="invalid-evidence", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    output = tmp_path / "campaign"
    CampaignExecutor(plan, output, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    ledger_path = output / "attempt-results.jsonl"
    record = json.loads(ledger_path.read_text(encoding="utf-8").strip())
    record["evidence_verified"] = False
    ledger_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = verify_campaign_archive(build_campaign_archive(output))
    assert result["valid"] is False
    assert any(issue["reason"] == "ledger_evidence_flag_invalid" for issue in result["issues"])
