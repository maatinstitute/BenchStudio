from reva.analysis import (
    ClaimType,
    OutcomeRecord,
    TimingProvenance,
    audit_campaign,
    audit_evaluation_acceptance,
    audit_execution_overhead,
)
from reva.campaigns import CampaignPlanner


def _complete_audit():
    plan = CampaignPlanner(
        run_id="acceptance", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    attempt_id = plan.attempts[0].key.attempt_id
    return audit_campaign(
        plan,
        [{"attempt_id": attempt_id, "status": "completed", "evidence_verified": True}],
        claim_type=ClaimType.SINGLE_RUN_OUTCOME,
        outcome_records=[
            OutcomeRecord(
                attempt_id,
                True,
                "official",
                "scorer",
                "rev",
                authoritative=True,
            )
        ],
    )


def test_acceptance_report_does_not_infer_missing_protocol_evidence():
    report = audit_evaluation_acceptance(_complete_audit())
    assert report.passed is False
    assert {check.requirement for check in report.checks if not check.passed} == {
        "policy_transparency",
        "reproducibility",
        "failure_recovery",
        "timing_correctness",
        "statistical_validity",
        "execution_overhead",
    }


def test_acceptance_report_passes_when_each_gate_has_explicit_evidence():
    overhead = audit_execution_overhead(
        [10.0],
        [11.0],
        deadline_ms=15.0,
        timing_provenance=TimingProvenance("host_monotonic", "start", "end"),
    )
    report = audit_evaluation_acceptance(
        _complete_audit(),
        policy_transparent=True,
        reproducible=True,
        recovery_verified=True,
        statistical_validity=True,
        execution_overhead=overhead,
    )
    assert report.passed is True
    assert report.to_dict()["schema"] == "reva_evaluation_acceptance_v1"
