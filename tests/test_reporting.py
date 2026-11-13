from __future__ import annotations

from reva import (
    build_audited_evaluation_report,
    build_evaluation_report,
    render_html_report,
    write_html_report,
)
from reva.analysis import (
    ClaimType,
    OutcomeRecord,
    audit_campaign,
    audit_evaluation_acceptance,
    summarize_paired_outcomes,
)
from reva.campaigns import CampaignPlanner


def test_paired_summary_reports_missingness_and_uncertainty():
    summary = summarize_paired_outcomes(
        [True, False, None], [False, True, True], [1.0, 2.0, None], [2.0, 1.0, 3.0]
    )
    assert summary.matched_pairs == 2
    assert summary.wins_a == 1
    assert summary.wins_b == 1
    assert summary.success_gap_b_minus_a == 0.0
    assert summary.success_gap_confidence_interval is not None
    assert summary.standard_error_numeric_delta == 1.0


def test_offline_report_round_trips_as_html(tmp_path):
    report = build_evaluation_report(
        title="Smoke",
        campaign={"run_id": "run-1"},
        outcomes={"success": 1},
        diagnostics={"coverage": "complete"},
        claim_decisions=[{"status": "supported"}],
    )
    html = render_html_report(report)
    assert "Smoke" in html
    assert "claim_decisions" in html
    path = tmp_path / "report.html"
    write_html_report(report, path)
    assert "&quot;schema&quot;" in path.read_text()


def test_audited_report_includes_claim_provenance_and_uncertainty():
    plan = CampaignPlanner(
        run_id="report-run", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    attempt_id = plan.attempts[0].key.attempt_id
    audit = audit_campaign(
        plan,
        [{"attempt_id": attempt_id, "status": "completed", "evidence_verified": True}],
        claim_type=ClaimType.SINGLE_RUN_OUTCOME,
        outcome_records=[
            OutcomeRecord(attempt_id, True, "official", "scorer", "rev", authoritative=True)
        ],
    )
    report = build_audited_evaluation_report(
        title="Audited",
        audit=audit,
        outcomes={"success_rate": 1.0},
        diagnostics={},
        paired_statistics=summarize_paired_outcomes([True], [False]),
        acceptance=audit_evaluation_acceptance(
            audit,
            policy_transparent=True,
            reproducible=True,
            recovery_verified=True,
            statistical_validity=True,
        ),
    )
    assert report["claim_decisions"][0]["status"] == "supported"
    assert report["campaign"]["outcome_provenance"]["authoritative_scorer_declared"]
    assert report["outcomes"]["paired_statistics"]["matched_pairs"] == 1
    assert report["acceptance"]["schema"] == "reva_evaluation_acceptance_v1"
