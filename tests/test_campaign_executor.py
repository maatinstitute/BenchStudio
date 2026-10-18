from __future__ import annotations

import json

from benchstudio.campaigns import CampaignExecutor, CampaignPlanner
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
