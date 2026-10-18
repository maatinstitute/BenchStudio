from __future__ import annotations

import json

from benchstudio.compare import build_comparison_report
from benchstudio.evidence import NdjsonWriter


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
            "sim-a": [{"success": True, "sim_time_s": 1.0, "final_joint_positions": {"j1": 0.0}}],
            "sim-b": [{"success": False, "sim_time_s": 2.0, "final_joint_positions": {"j1": 0.2}}],
        },
    )
    pair = report["divergence"]["sim-a_vs_sim-b"]
    assert pair["success_agreement_rate"] == 0.0
    assert pair["episodes"][0]["final_joint_rmse_rad"] == 0.2
