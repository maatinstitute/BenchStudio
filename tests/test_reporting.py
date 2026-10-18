from __future__ import annotations

from benchstudio import build_evaluation_report, render_html_report, write_html_report
from benchstudio.analysis import summarize_paired_outcomes


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
