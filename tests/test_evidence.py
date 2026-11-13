from __future__ import annotations

import json

from ival.compare import build_comparison_report
from ival.evidence import NdjsonWriter, environment_fingerprint, verify_artifact_manifest
from ival.mock import MockPolicy, MockSimulator
from ival.runner import RunConfig, run_episodes


def test_ndjson_writer_returns_digest_and_count(tmp_path):
    writer = NdjsonWriter(tmp_path / "trace.ndjson")
    writer.write({"t_ms": 0, "stream": "state"})
    artifact = writer.close()
    assert artifact["record_count"] == 1
    assert len(artifact["digest_sha256"]) == 64
    assert json.loads((tmp_path / "trace.ndjson").read_text())["t_ms"] == 0


def test_environment_fingerprint_records_optional_backend_versions(monkeypatch):
    from ival import evidence

    versions = {
        "ival": "0.1.0",
        "mujoco": "3.3.0",
        "gymnasium": "1.0.0",
        "genesis-world": "1.4.0",
        "isaaclab": "2.0.0",
        "usd-core": "24.0",
        "numpy": "2.0.0",
        "scipy": "1.14.0",
    }

    def fake_version(name):
        if name not in versions:
            raise evidence.metadata.PackageNotFoundError(name)
        return versions[name]

    monkeypatch.setattr(evidence.metadata, "version", fake_version)
    fingerprint = environment_fingerprint("isaaclab")
    assert fingerprint["backend_id"] == "isaaclab"
    assert fingerprint["packages"]["ival"] == "0.1.0"
    assert fingerprint["packages"]["gymnasium"] == "1.0.0"
    assert fingerprint["packages"]["isaaclab"] == "2.0.0"


def test_comparison_preserves_backend_divergence():
    report = build_comparison_report(
        scenario_id="table30-task-1",
        per_backend_reports={
            "sim-a": [
                {
                    "pair_id": "seed-1",
                    "condition_id": "condition-a",
                    "success": True,
                    "sim_time_s": 1.0,
                    "final_joint_positions": {"j1": 0.0},
                }
            ],
            "sim-b": [
                {
                    "pair_id": "seed-1",
                    "condition_id": "condition-b",
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

    with pytest.raises(ValueError, match="pair_id"):
        build_comparison_report(
            scenario_id="task",
            per_backend_reports={"a": [{"success": True}], "b": [{"success": True}]},
        )


def test_comparison_ignores_nonfinite_joint_values():
    report = build_comparison_report(
        scenario_id="task",
        per_backend_reports={
            "a": [{"pair_id": "p", "success": True, "final_joint_positions": {"j": "bad"}}],
            "b": [{"pair_id": "p", "success": True, "final_joint_positions": {"j": 0.2}}],
        },
    )
    assert report["divergence"]["a_vs_b"]["episodes"][0]["final_joint_rmse_rad"] is None


def test_comparison_ignores_coerced_and_invalid_timing_values():
    report = build_comparison_report(
        scenario_id="task",
        per_backend_reports={
            "a": [
                {
                    "pair_id": "p",
                    "success": True,
                    "wall_time_s": "1.0",
                    "sim_time_s": True,
                }
            ],
            "b": [
                {
                    "pair_id": "p",
                    "success": True,
                    "wall_time_s": True,
                    "sim_time_s": "2.0",
                }
            ],
        },
    )
    assert report["summary"]["a"]["mean_wall_time_s"] is None
    assert report["summary"]["b"]["mean_wall_time_s"] is None
    assert report["summary"]["a"]["mean_time_to_success_s"] is None


def test_run_artifact_manifest_detects_trace_tampering(tmp_path):
    run_dir = tmp_path / "run"
    run_episodes(MockPolicy(), MockSimulator(), RunConfig(episodes=1), run_dir)
    result = verify_artifact_manifest(run_dir)
    assert result["valid"] is True
    assert result["trust_anchor"]["checked"] is True
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


def test_artifact_manifest_requires_external_trust_anchor(tmp_path):
    run_dir = tmp_path / "run"
    run_episodes(MockPolicy(), MockSimulator(), RunConfig(episodes=1), run_dir)
    (tmp_path / "run.artifact-manifest.sha256").unlink()
    result = verify_artifact_manifest(run_dir)
    assert result["valid"] is False
    assert {item["reason"] for item in result["mismatches"]} == {"trust_anchor_missing"}


def test_artifact_manifest_can_check_independent_trusted_digest(tmp_path):
    run_dir = tmp_path / "run"
    run_episodes(MockPolicy(), MockSimulator(), RunConfig(episodes=1), run_dir)
    from ival.evidence import sha256_file

    digest = sha256_file(run_dir / "artifact-manifest.json")
    result = verify_artifact_manifest(run_dir, trusted_manifest_sha256=digest)
    assert result["valid"] is True
    result = verify_artifact_manifest(run_dir, trusted_manifest_sha256="0" * 64)
    assert result["valid"] is False
    assert "external_trust_reference_mismatch" in {item["reason"] for item in result["mismatches"]}


def test_artifact_manifest_verifier_returns_structured_missing_manifest_error(tmp_path):
    result = verify_artifact_manifest(tmp_path / "missing")
    assert result["valid"] is False
    assert "artifact_root_missing" in {item["reason"] for item in result["mismatches"]}


def test_artifact_manifest_verifier_rejects_malformed_manifest(tmp_path):
    run_dir = tmp_path / "malformed"
    run_dir.mkdir()
    (run_dir / "artifact-manifest.json").write_text("not-json")
    result = verify_artifact_manifest(run_dir)
    assert result["valid"] is False
    assert "manifest_invalid_json" in {item["reason"] for item in result["mismatches"]}


def test_artifact_manifest_verifier_rejects_path_escape(tmp_path):
    run_dir = tmp_path / "escape"
    run_dir.mkdir()
    (run_dir / "artifact-manifest.json").write_text(
        json.dumps(
            {
                "schema": "ival_artifact_manifest_v1",
                "status": "completed",
                "files": {"../outside": {"sha256": "0" * 64, "bytes": 1}},
            }
        )
    )
    result = verify_artifact_manifest(run_dir)
    assert result["valid"] is False
    assert "manifest_path_escape" in {item["reason"] for item in result["mismatches"]}


def test_artifact_manifest_verifier_rejects_malformed_file_entry(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "artifact-manifest.json").write_text(
        json.dumps(
            {
                "schema": "ival_artifact_manifest_v1",
                "status": "completed",
                "files": {"trace.jsonl": {"sha256": "not-a-digest", "bytes": "1"}},
            }
        ),
        encoding="utf-8",
    )
    result = verify_artifact_manifest(run_dir)
    reasons = {item["reason"] for item in result["mismatches"]}
    assert {"manifest_digest_invalid", "manifest_size_invalid"} <= reasons


def test_artifact_manifest_creation_rejects_symlinks(tmp_path):
    import pytest

    root = tmp_path / "run"
    root.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    (root / "trace.jsonl").symlink_to(target)
    with pytest.raises(ValueError, match="contains symlink"):
        from ival.evidence import build_artifact_manifest

        build_artifact_manifest(root, status="completed")


def test_artifact_manifest_verifier_rejects_symlinked_bound_file(tmp_path):
    run_dir = tmp_path / "symlink"
    run_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    linked = run_dir / "linked.txt"
    linked.symlink_to(outside)
    (run_dir / "artifact-manifest.json").write_text(
        json.dumps(
            {
                "schema": "ival_artifact_manifest_v1",
                "status": "completed",
                "files": {"linked.txt": {"sha256": "0" * 64, "bytes": 7}},
            }
        )
    )
    result = verify_artifact_manifest(run_dir)
    assert result["valid"] is False
    assert "symlink_artifact" in {item["reason"] for item in result["mismatches"]}
