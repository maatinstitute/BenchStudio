from __future__ import annotations

import json

from benchstudio import build_runtime_receipt, verify_runtime_receipt, write_runtime_receipt


def test_runtime_receipt_is_digest_verifiable_and_persisted(tmp_path):
    receipt = build_runtime_receipt(
        run_id="run",
        attempt_id="attempt-1",
        plan_digest_sha256="a" * 64,
        worker_id="worker-1",
        status="completed",
        started_monotonic_ns=10,
        completed_monotonic_ns=25,
        backend_id="mock_simulator",
        environment={"python": "3.13"},
    )
    path = tmp_path / "runtime-receipt.json"
    write_runtime_receipt(path, receipt)
    assert verify_runtime_receipt(path)["valid"] is True
    assert json.loads(path.read_text())["duration_ns"] == 15


def test_runtime_receipt_detects_tampering():
    receipt = build_runtime_receipt(
        run_id=None,
        attempt_id=None,
        plan_digest_sha256=None,
        worker_id=None,
        status="completed",
        started_monotonic_ns=10,
        completed_monotonic_ns=10,
        backend_id="mock",
        environment={},
    )
    tampered = {**receipt, "status": "failed"}
    result = verify_runtime_receipt(tampered)
    assert result == {"valid": False, "reason": "receipt_digest_mismatch"}
