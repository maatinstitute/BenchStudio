from __future__ import annotations

import json

from ival.analysis import load_smolvla_deployment_evidence


def _manifest() -> dict:
    return {
        "checkpoint": "HuggingFaceVLA/smolvla_libero",
        "checkpoint_revision": "a" * 40,
        "lerobot_revision": "b" * 40,
        "environment": "LIBERO libero_spatial",
        "task_ids_primary": [0],
        "suite_gate": {"libero_spatial": 1.0},
        "seed": 1000,
        "primary_episodes": 2,
        "denoising_steps_primary": 10,
        "device": "cuda",
        "ledger_version": 1,
        "instrumentation": ["select_action_calls"],
        "timing_limitations": "aggregate host timing",
        "pairing_status": "pairing is unverified",
        "scope": "deployment accounting pilot",
    }


def _row() -> dict:
    return {
        "n_action_steps": 10,
        "control_steps": 20,
        "neural_chunk_calls": 4,
        "control_to_neural": 5.0,
        "successes": [True, False],
        "success_rate_percent": 50.0,
        "eval_seconds": 2.0,
        "neural_p50_seconds": 0.2,
        "neural_p95_seconds": 0.3,
    }


def test_archived_deployment_evidence_validates_arithmetic(tmp_path):
    manifest = tmp_path / "manifest.json"
    summary = tmp_path / "summary.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    summary.write_text(json.dumps([_row()]), encoding="utf-8")
    report = load_smolvla_deployment_evidence(manifest, summary)
    assert report["valid"] is True
    assert report["execution_status"] == "archived_external_evidence"
    assert report["weights_and_runtime"] == "external"
    assert len(report["manifest_sha256"]) == 64


def test_archived_deployment_evidence_rejects_inconsistent_ratio(tmp_path):
    manifest = tmp_path / "manifest.json"
    summary = tmp_path / "summary.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    row = _row()
    row["control_to_neural"] = 4.0
    summary.write_text(json.dumps([row]), encoding="utf-8")
    report = load_smolvla_deployment_evidence(manifest, summary)
    assert report["valid"] is False
    assert any("control_to_neural" in issue for issue in report["issues"])


def test_archived_deployment_evidence_rejects_invalid_revision(tmp_path):
    manifest = tmp_path / "manifest.json"
    summary = tmp_path / "summary.json"
    value = _manifest()
    value["checkpoint_revision"] = "not-a-commit"
    manifest.write_text(json.dumps(value), encoding="utf-8")
    summary.write_text(json.dumps([_row()]), encoding="utf-8")
    report = load_smolvla_deployment_evidence(manifest, summary)
    assert report["valid"] is False
    assert any("checkpoint_revision" in issue for issue in report["issues"])


def test_archived_deployment_evidence_requires_independent_digests(tmp_path):
    manifest = tmp_path / "manifest.json"
    summary = tmp_path / "summary.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    summary.write_text(json.dumps([_row()]), encoding="utf-8")
    trusted = load_smolvla_deployment_evidence(manifest, summary)
    verified = load_smolvla_deployment_evidence(
        manifest,
        summary,
        expected_manifest_sha256=trusted["manifest_sha256"],
        expected_summary_sha256=trusted["summary_sha256"],
    )
    assert verified["valid"] is True
    rejected = load_smolvla_deployment_evidence(
        manifest, summary, expected_manifest_sha256="0" * 64
    )
    assert rejected["valid"] is False
    assert any("independently supplied digest" in issue for issue in rejected["issues"])
