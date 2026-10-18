from __future__ import annotations

import json

from benchstudio.analysis import ClaimType
from benchstudio.campaigns import (
    CampaignExecutor,
    CampaignPlanner,
    WorkerLeaseManager,
    compile_campaign_spec,
)
from benchstudio.mock import MockPolicy, MockSimulator


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
