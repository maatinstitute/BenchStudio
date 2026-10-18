from __future__ import annotations

import json

from benchstudio.campaigns import compile_campaign_spec
from benchstudio.compare import build_campaign_comparison_report, build_comparison_report


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


def test_campaign_comparison_loads_frozen_attempts_in_plan_order(tmp_path):
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "compare"},
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"id": "a"}, {"id": "b"}],
            },
        }
    )
    roots = {name: tmp_path / name for name in ("left", "right")}
    for root in roots.values():
        (root / "attempts").mkdir(parents=True)
        (root / "campaign-plan.json").write_text(json.dumps(plan.to_dict()), encoding="utf-8")
    for index, attempt in enumerate(plan.attempts):
        attempt_id = attempt.key.attempt_id
        report = {
            "episode_id": attempt_id,
            "pair_id": attempt.key.pair_id,
            "condition_id": attempt.key.condition_id,
            "success": index == 0,
            "status": "success" if index == 0 else "failure",
            "wall_time_s": 0.1,
        }
        for root in roots.values():
            attempt_dir = root / "attempts" / attempt_id
            attempt_dir.mkdir()
            (attempt_dir / "summary.json").write_text(
                json.dumps({"episodes": [report]}), encoding="utf-8"
            )
    (roots["left"] / "attempts" / plan.attempts[1].key.attempt_id / "summary.json").unlink()
    report = build_campaign_comparison_report(scenario_id="task", backend_campaigns=roots)
    summary = report["summary"]["left"]
    assert summary["scheduled"] == 2
    assert summary["completed"] == 1
    assert summary["missing"] == 1
    assert report["divergence"]["left_vs_right"]["compared_episodes"] == 1


def test_campaign_comparison_preserves_malformed_attempts_as_failures(tmp_path):
    root = tmp_path / "backend"
    (root / "attempts" / "attempt-1").mkdir(parents=True)
    (root / "campaign-plan.json").write_text(
        json.dumps({"attempts": [{"key": {"attempt_id": "attempt-1"}}]}), encoding="utf-8"
    )
    (root / "attempts" / "attempt-1" / "summary.json").write_text("not-json", encoding="utf-8")
    report = build_campaign_comparison_report(scenario_id="task", backend_campaigns={"x": root})
    assert report["summary"]["x"]["failed"] == 1
    assert report["errors"]["x"]


def test_campaign_comparison_adds_transfer_fidelity_for_named_backends(tmp_path):
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "transfer-compare"},
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {"seeds": [1], "paired": True, "conditions": [{"id": "base"}]},
        }
    )
    roots = {name: tmp_path / name for name in ("simulation", "physical")}
    for root in roots.values():
        attempt = plan.attempts[0]
        attempt_dir = root / "attempts" / attempt.key.attempt_id
        attempt_dir.mkdir(parents=True)
        (root / "campaign-plan.json").write_text(json.dumps(plan.to_dict()), encoding="utf-8")
        (attempt_dir / "summary.json").write_text(
            json.dumps(
                {
                    "episodes": [
                        {
                            "pair_id": attempt.key.pair_id,
                            "condition_id": attempt.key.condition_id,
                            "status": "success",
                            "success": root.name == "simulation",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
    report = build_campaign_comparison_report(
        scenario_id="task",
        backend_campaigns=roots,
        transfer_backends=("simulation", "physical"),
    )
    transfer = report["transfer_fidelity"]
    assert transfer["schema"] == "benchstudio_transfer_fidelity_report_v1"
    assert transfer["success_gap_physical_minus_simulation"] == -1.0
