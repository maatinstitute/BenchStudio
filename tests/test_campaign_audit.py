from benchstudio.analysis import ClaimType, audit_campaign
from benchstudio.campaigns import CampaignPlanner


def test_campaign_audit_derives_supported_claim_from_verified_complete_ledger():
    plan = CampaignPlanner(
        run_id="run", scenario_id="task", conditions=[{"x": 1}], seeds=[1, 2]
    ).freeze()
    records = [
        {
            "attempt_id": attempt.key.attempt_id,
            "status": "completed",
            "evidence_verified": True,
        }
        for attempt in plan.attempts
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


def test_campaign_audit_keeps_missing_attempts_from_becoming_supported_claims():
    plan = CampaignPlanner(
        run_id="run", scenario_id="task", conditions=[{"x": 1}], seeds=[1, 2]
    ).freeze()
    audit = audit_campaign(
        plan,
        [
            {
                "attempt_id": plan.attempts[0].key.attempt_id,
                "status": "completed",
                "evidence_verified": True,
            }
        ],
        claim_type=ClaimType.SINGLE_RUN_OUTCOME,
        evidence={"authoritative_scorer_declared": True},
    )
    assert audit.missing_attempt_ids == ("attempt-000001",)
    assert audit.claim.status == "qualified"
