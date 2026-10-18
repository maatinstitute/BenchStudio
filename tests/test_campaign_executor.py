from __future__ import annotations

import json

from benchstudio.campaigns import CampaignExecutor, CampaignPlanner, WorkerLeaseManager
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
