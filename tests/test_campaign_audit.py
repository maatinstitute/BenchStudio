from benchstudio.analysis import ClaimType, OutcomeRecord, audit_campaign
from benchstudio.analysis.campaign_audit import _runtime_environment_issues
from benchstudio.campaigns import CampaignPlanner, compile_campaign_spec


def test_runtime_environment_audit_detects_software_drift_within_one_environment():
    issues = _runtime_environment_issues(
        [
            (
                "sim",
                "attempt-1",
                {"python": "3.12.12", "packages": {"torch": "2.7.1"}, "backend_id": "libero"},
            ),
            (
                "sim",
                "attempt-2",
                {"python": "3.12.12", "packages": {"torch": "2.8.0"}, "backend_id": "libero"},
            ),
        ]
    )
    assert issues == (
        "attempt-2: runtime software differs from attempt-1 within environment sim",
    )


def test_runtime_environment_audit_keeps_declared_environments_separate():
    assert _runtime_environment_issues(
        [
            ("sim-a", "attempt-1", {"python": "3.11", "packages": {}, "backend_id": "a"}),
            ("sim-b", "attempt-2", {"python": "3.12", "packages": {}, "backend_id": "b"}),
        ]
    ) == ()


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


def test_campaign_audit_exposes_unverified_imported_source_gates():
    plan = CampaignPlanner(
        run_id="source-gates",
        scenario_id="task",
        conditions=[{"x": 1}],
        seeds=[1],
        protocol={
            "source_status": "requires_runtime_and_holdout_verification",
            "external_gates": {
                "runtime": "unverified",
                "holdout": "unverified",
            },
        },
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
    )
    assert audit.source_status == "requires_runtime_and_holdout_verification"
    assert audit.source_gates_verified is False
    assert audit.source_gate_issues == (
        "external gate holdout is not verified: 'unverified'",
        "external gate runtime is not verified: 'unverified'",
    )
    assert audit.to_dict()["source_gates_verified"] is False


def test_campaign_audit_fail_closes_on_malformed_source_gate_values():
    plan = CampaignPlanner(
        run_id="malformed-source-gates",
        scenario_id="task",
        conditions=[{"x": 1}],
        seeds=[1],
        protocol={"external_gates": {"runtime": {"status": "verified"}}},
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
    )
    assert audit.source_gates_verified is False
    assert "external gate runtime is not verified" in audit.source_gate_issues[0]
