import json

from benchstudio.demo_dashboard import build_demo_dashboard


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_demo_dashboard_renders_artifact_values_and_urdf_studio_theme(tmp_path):
    evidence = tmp_path / "evidence"
    attempts = []
    ledger = []
    for index, condition in enumerate(("baseline", "low_refinement")):
        attempt_id = f"attempt-{index:06d}"
        attempts.append(
            {
                "key": {
                    "attempt_id": attempt_id,
                    "condition_id": condition,
                    "pair_id": "pair-01",
                },
                "metadata": {
                    "condition": {
                        "id": condition,
                        "denoising_steps": 10 if index == 0 else 2,
                    }
                },
            }
        )
        ledger.append(
            {
                "attempt_id": attempt_id,
                "status": "completed",
                "success_count": 1,
                "evidence_verified": True,
            }
        )

    _write_json(
        evidence / "campaign-plan.json",
        {
            "run_id": "pink-demo",
            "plan_digest_sha256": "abc123def456",
            "attempts": attempts,
        },
    )
    ledger_path = evidence / "campaign" / "attempt-results.jsonl"
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        "\n".join(json.dumps(row) for row in ledger) + "\n", encoding="utf-8"
    )
    _write_json(
        evidence / "robustness" / "counterfactual-summary.json",
        {
            "scheduled_branch_count": 2,
            "completed_branch_count": 2,
            "result_digest_sha256": "robust123",
        },
    )
    _write_json(
        evidence / "transfer" / "transfer-report.json",
        {
            "transfer_fidelity": {
                "simulation_success_rate": 1.0,
                "physical_success_rate": 0.5,
                "success_gap_physical_minus_simulation": -0.5,
                "matched_pairs": 2,
            }
        },
    )
    _write_json(
        evidence / "robochallenge-report.json", {"valid": True, "event_count": 2}
    )

    output = build_demo_dashboard(evidence, tmp_path / "site" / "index.html")
    document = output.read_text(encoding="utf-8")

    assert "BenchStudio Evaluation Control Room" in document
    assert "pink-demo" in document
    assert '"attempts.scheduled"</span>: <span class="json-number">2</span>' in document
    assert '"transport.valid"</span>: <span class="json-ok">true</span>' in document
    assert "--pink: #ff4fba" in document
    assert "Inspect complete JSON" in document
