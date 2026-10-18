from benchstudio.analysis import ClaimType, OutcomeRecord, audit_campaign
from benchstudio.campaigns import CampaignPlanner, compile_campaign_spec


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


def test_campaign_audit_requires_authoritative_outcome_provenance():
    plan = CampaignPlanner(
        run_id="run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    records = [
        {
            "attempt_id": plan.attempts[0].key.attempt_id,
            "status": "completed",
            "evidence_verified": True,
        }
    ]
    audit = audit_campaign(
        plan,
        records,
        claim_type=ClaimType.SINGLE_RUN_OUTCOME,
        evidence={"authoritative_scorer_declared": True},
        outcome_records=[OutcomeRecord(plan.attempts[0].key.attempt_id, True, "supplementary")],
    )
    assert audit.outcome_provenance is not None
    assert audit.claim.status == "qualified"


def test_campaign_audit_does_not_promote_infrastructure_failure_to_task_outcome():
    plan = CampaignPlanner(
        run_id="infra-outcome", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    attempt_id = plan.attempts[0].key.attempt_id
    audit = audit_campaign(
        plan,
        [{"attempt_id": attempt_id, "status": "infrastructure_failure", "evidence_verified": True}],
        claim_type=ClaimType.SINGLE_RUN_OUTCOME,
        evidence={"authoritative_scorer_declared": True},
        outcome_records=[OutcomeRecord(attempt_id, True, "official", "scorer", "rev", True)],
    )
    assert audit.claim.status == "unsupported"
    assert audit.claim.prerequisites["outcome_present"] is False


def test_campaign_audit_rejects_paired_claim_with_incompatible_calibration():
    def digest(char):
        return "sha256:" + char * 64

    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "paired-calibration"},
            "task": {"task_id": "task"},
            "environments": [
                {
                    "id": "sim",
                    "kind": "simulator",
                    "calibration": {
                        "revision": "v1",
                        "camera": digest("1"),
                        "action_transform": digest("2"),
                    },
                },
                {
                    "id": "real",
                    "kind": "physical",
                    "enabled": True,
                    "requires_authorization": True,
                    "retry_policy": "none",
                    "calibration": {
                        "revision": "v1",
                        "camera": digest("9"),
                        "action_transform": digest("2"),
                    },
                },
            ],
            "evaluation": {"seeds": [1], "paired": True, "conditions": [{"x": 1}]},
        }
    )
    records = [
        {"attempt_id": attempt.key.attempt_id, "status": "completed", "evidence_verified": True}
        for attempt in plan.attempts
    ]
    audit = audit_campaign(
        plan,
        records,
        claim_type=ClaimType.PAIRED_COMPARISON,
        evidence={
            "outcome_present": True,
            "paired_conditions": True,
            "semantic_match": True,
            "uncertainty_reported": True,
        },
    )
    assert audit.claim.status == "unsupported"
    assert "sim vs real: camera calibration differs" in audit.calibration_issues
    assert audit.claim.prerequisites["semantic_match"] is False


def test_campaign_audit_exposes_missing_benchmark_validity():
    plan = CampaignPlanner(
        run_id="run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    records = [
        {"attempt_id": attempt.key.attempt_id, "status": "completed", "evidence_verified": True}
        for attempt in plan.attempts
    ]
    audit = audit_campaign(
        plan,
        records,
        claim_type=ClaimType.PAIRED_COMPARISON,
        evidence={
            "outcome_present": True,
            "paired_conditions": True,
            "semantic_match": True,
            "uncertainty_reported": True,
        },
    )
    assert audit.benchmark_validity is None
    assert audit.claim.prerequisites["semantic_match"] is False
