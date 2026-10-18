from __future__ import annotations

import json

from benchstudio.compare import build_comparison_report
from benchstudio.evidence import NdjsonWriter, verify_artifact_manifest
from benchstudio.mock import MockPolicy, MockSimulator
from benchstudio.runner import RunConfig, run_episodes


def test_ndjson_writer_returns_digest_and_count(tmp_path):
    writer = NdjsonWriter(tmp_path / "trace.ndjson")
    writer.write({"t_ms": 0, "stream": "state"})
    artifact = writer.close()
    assert artifact["record_count"] == 1
    assert len(artifact["digest_sha256"]) == 64
    assert json.loads((tmp_path / "trace.ndjson").read_text())["t_ms"] == 0


def test_comparison_preserves_backend_divergence():
    report = build_comparison_report(
        scenario_id="table30-task-1",
        per_backend_reports={
            "sim-a": [
                {
                    "episode_id": "seed-1",
                    "success": True,
                    "sim_time_s": 1.0,
                    "final_joint_positions": {"j1": 0.0},
                }
            ],
            "sim-b": [
                {
                    "episode_id": "seed-1",
                    "success": False,
                    "sim_time_s": 2.0,
                    "final_joint_positions": {"j1": 0.2},
                }
            ],
        },
    )
    pair = report["divergence"]["sim-a_vs_sim-b"]
    assert pair["success_agreement_rate"] == 0.0
    assert pair["episodes"][0]["final_joint_rmse_rad"] == 0.2


def test_comparison_rejects_reports_without_stable_identity():
    import pytest

    with pytest.raises(ValueError, match="episode_id"):
        build_comparison_report(
            scenario_id="task",
            per_backend_reports={"a": [{"success": True}], "b": [{"success": True}]},
        )


def test_run_artifact_manifest_detects_trace_tampering(tmp_path):
    run_dir = tmp_path / "run"
    run_episodes(MockPolicy(), MockSimulator(), RunConfig(episodes=1), run_dir)
    assert verify_artifact_manifest(run_dir)["valid"] is True
    with (run_dir / "episodes.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")
    result = verify_artifact_manifest(run_dir)
    assert result["valid"] is False
    assert result["mismatches"][0]["file"] == "episodes.jsonl"


def test_artifact_manifest_rejects_unbound_files(tmp_path):
    run_dir = tmp_path / "run"
    run_episodes(MockPolicy(), MockSimulator(), RunConfig(episodes=1), run_dir)
    (run_dir / "unexpected.bin").write_bytes(b"outside the manifest")
    result = verify_artifact_manifest(run_dir)
    assert result["valid"] is False
    assert {item["reason"] for item in result["mismatches"]} == {"unbound_artifact"}
