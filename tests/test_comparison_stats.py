from __future__ import annotations

from benchstudio.compare import build_comparison_report


def test_comparison_exposes_scheduled_and_completed_denominators():
    report = build_comparison_report(
        scenario_id="task",
        per_backend_reports={
            "sim-a": [
                {"episode_id": "seed-1", "success": True},
                None,
            ],
        },
    )
    summary = report["summary"]["sim-a"]
    assert summary["episodes"] == 2
    assert summary["completed"] == 1
    assert summary["missing"] == 1
    assert summary["completed_success_rate"] == 1.0
    assert summary["scheduled_success_rate"] == 0.5
