import json

from benchstudio.analysis import ClaimType, audit_campaign
from benchstudio.campaigns import CampaignExecutor, compile_campaign_spec
from benchstudio.mock import MockPolicy, MockSimulator


def test_frozen_campaign_ci_smoke_is_end_to_end(tmp_path):
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "ci-smoke"},
            "model": {"adapter": "mock"},
            "task": {"task_id": "mock-task"},
            "environments": [{"id": "mock", "kind": "simulator"}],
            "evaluation": {
                "seeds": [10, 11],
                "paired": True,
                "missing_outcomes": "preserve",
                "confirmation_plan": "frozen",
                "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
            },
        }
    )
    output = tmp_path / "campaign"
    result = CampaignExecutor(
        plan,
        output,
        lambda _attempt: MockPolicy(),
        lambda _attempt: MockSimulator(),
    ).run()
    assert result.missing_attempt_ids == ()
    records = [
        json.loads(line)
        for line in (output / "attempt-results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    audit = audit_campaign(
        plan,
        records,
        claim_type=ClaimType.SINGLE_RUN_OUTCOME,
        evidence={"authoritative_scorer_declared": True},
    )
    assert audit.attempts_complete is True
    assert audit.evidence_verified is True
    assert audit.claim.status == "supported"
