from __future__ import annotations

import json

import pytest

from benchstudio.campaigns import AttemptLedger, CampaignPlanner


def test_frozen_campaign_has_stable_complete_matrix(tmp_path):
    plan = CampaignPlanner(
        run_id="run-1",
        scenario_id="pick",
        conditions=[{"budget": 2}, {"budget": 4}],
        seeds=[1, 2],
        repetitions=2,
    ).freeze()
    assert len(plan.attempts) == 8
    assert len({attempt.key.pair_id for attempt in plan.attempts}) == 2
    assert len({attempt.key.condition_id for attempt in plan.attempts}) == 2
    assert len(plan.plan_digest_sha256) == 64
    plan.write(tmp_path / "plan.json")
    assert (
        json.loads((tmp_path / "plan.json").read_text())["plan_digest_sha256"]
        == plan.plan_digest_sha256
    )


def test_attempt_ledger_is_append_only_and_reports_missing(tmp_path):
    plan = CampaignPlanner(
        run_id="run-1", scenario_id="pick", conditions=[{"budget": 2}], seeds=[1, 2]
    ).freeze()
    ledger = AttemptLedger(tmp_path / "attempts.jsonl", plan)
    first = plan.attempts[0].key
    ledger.append(first, {"status": "success"})
    assert ledger.missing_attempt_ids == [plan.attempts[1].key.attempt_id]
    with pytest.raises(ValueError, match="already recorded"):
        ledger.append(first, {"status": "success"})
    wrong = type(first)(
        first.run_id, first.scenario_id, "other", first.condition_id, first.attempt_id
    )
    with pytest.raises(ValueError, match="identity"):
        ledger.append(wrong, {"status": "success"})


def test_attempt_ledger_rejects_reopening_with_a_different_plan(tmp_path):
    path = tmp_path / "attempts.jsonl"
    plan = CampaignPlanner(
        run_id="run-1", scenario_id="pick", conditions=[{"budget": 2}], seeds=[1]
    ).freeze()
    AttemptLedger(path, plan).append(plan.attempts[0].key, {"status": "success"})
    other = CampaignPlanner(
        run_id="run-1", scenario_id="pick", conditions=[{"budget": 4}], seeds=[1]
    ).freeze()
    with pytest.raises(ValueError, match="plan digest"):
        AttemptLedger(path, other)
