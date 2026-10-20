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
    _write_json(
        evidence / "urdf-studio" / "run.json",
        {"schema": "scenario_run.v1", "scenario_id": "so101_cube_lift", "sims": ["mujoco"]},
    )
    _write_json(
        evidence / "urdf-studio" / "comparison.json",
        {"scenario_id": "so101_cube_lift", "backends": {"mujoco": {"success_rate": 1.0}}},
    )
    _write_json(
        evidence / "urdf-studio" / "mujoco" / "episode-0" / "report.json",
        {
            "success": True,
            "sim_time_s": 1.5,
            "wall_time_s": 0.4,
            "steps": 75,
            "artifacts": {"trace_ndjson": {"record_count": 225}},
            "environment": {"packages": {"mujoco": "3.12.0"}},
        },
    )

    output = build_demo_dashboard(evidence, tmp_path / "site" / "index.html")
    document = output.read_text(encoding="utf-8")

    assert "BenchStudio — Evaluation report" in document
    assert "Eval Control Room" in document
    assert "Scientific verdict" not in document
    assert "EVIDENCE QUALIFIED" not in document
    assert "pink-demo" in document
    assert '"attempts.scheduled"</span>: <span class="json-number">2</span>' in document
    assert '"transport.valid"</span>: <span class="json-ok">true</span>' in document
    assert 'font-family:"Noto Sans", Arial, sans-serif' in document
    assert "--pink:#ff4fba" in document
    assert "radial-gradient" not in document
    assert "text-shadow" not in document
    assert "VIEW MACHINE-READABLE SUMMARY" in document
    assert 'data-artifact="plan"' in document
    assert 'href="campaign-plan.json"' not in document
    assert "SO-101 · Cube lift" in document
    assert "urdf-studio/mujoco/episode-0/episode.mp4" in document
    assert 'value="mujoco" selected>MuJoCo · evaluated' in document
    assert 'value="genesis" disabled>Genesis · run required' in document
    assert "this report stays bound to the evaluated episode" in document
    assert "225</b>" in document
    assert 'data-artifact="robot_episode"' in document
