from __future__ import annotations

from benchstudio.compare import build_comparison_report


def test_comparison_exposes_scheduled_and_completed_denominators():
    report = build_comparison_report(
        scenario_id="task",
        per_backend_reports={
            "sim-a": [
                {"pair_id": "seed-1", "condition_id": "condition-a", "success": True},
                None,
            ],
        },
    )
    summary = report["summary"]["sim-a"]
    assert summary["episodes"] == 2
    assert summary["completed"] == 1
    assert summary["missing"] == 1
    assert summary["completed_success_rate"] == 1.0
    assert summary["completed_success_confidence_interval"] is not None
    assert summary["scheduled_success_rate"] == 0.5
    assert summary["scheduled_success_confidence_interval"] is not None


def test_comparison_separates_execution_failures_from_task_outcomes():
    report = build_comparison_report(
        scenario_id="task",
        per_backend_reports={
            "sim-a": [
                {"pair_id": "seed-1", "status": "policy_inference_error", "success": False},
                {"pair_id": "seed-2", "status": "success", "success": True},
            ],
            "sim-b": [
                {"pair_id": "seed-1", "status": "failure", "success": False},
                {"pair_id": "seed-2", "status": "success", "success": True},
            ],
        },
    )
    summary = report["summary"]["sim-a"]
    assert summary["scheduled"] == 2
    assert summary["completed"] == 1
    assert summary["failed"] == 1
    assert summary["missing"] == 0
    divergence = report["divergence"]["sim-a_vs_sim-b"]
    assert divergence["compared_episodes"] == 1
    assert divergence["success_agreement_confidence_interval"] is not None
    assert divergence["failed_a"] == ["seed-1"]
