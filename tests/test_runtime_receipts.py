from __future__ import annotations

import hashlib
import json

from benchstudio import (
    build_runtime_receipt,
    generate_ed25519_keypair,
    sign_runtime_receipt,
    verify_runtime_receipt,
    verify_runtime_receipt_signature,
    write_runtime_receipt,
)


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


def test_runtime_receipt_rejects_rehashed_malformed_fields():
    receipt = build_runtime_receipt(
        run_id="run",
        attempt_id="attempt",
        plan_digest_sha256="a" * 64,
        worker_id=None,
        status="completed",
        started_monotonic_ns=10,
        completed_monotonic_ns=20,
        backend_id="sim",
        environment={},
    )
    malformed = {**receipt, "started_monotonic_ns": "10"}
    payload = {key: value for key, value in malformed.items() if key != "receipt_digest_sha256"}
    malformed["receipt_digest_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert verify_runtime_receipt(malformed) == {
        "valid": False,
        "reason": "timing_fields_invalid",
    }


def test_runtime_receipt_rejects_invalid_build_types():
    import pytest

    with pytest.raises(ValueError, match="environment must be a mapping"):
        build_runtime_receipt(
            run_id="run",
            attempt_id="attempt",
            plan_digest_sha256=None,
            worker_id=None,
            status="completed",
            started_monotonic_ns=0,
            completed_monotonic_ns=1,
            backend_id="sim",
            environment=[],  # type: ignore[arg-type]
        )


def test_runtime_receipt_signature_is_independently_verifiable(tmp_path):
    receipt = build_runtime_receipt(
        run_id="run",
        attempt_id="attempt-1",
        plan_digest_sha256=None,
        worker_id="worker-1",
        status="completed",
        started_monotonic_ns=1,
        completed_monotonic_ns=2,
        backend_id="mock",
        environment={},
    )
    receipt_path = tmp_path / "receipt.json"
    signature_path = tmp_path / "receipt.sig"
    write_runtime_receipt(receipt_path, receipt)
    private_key, public_key = generate_ed25519_keypair()
    sign_runtime_receipt(receipt_path, private_key, signature_path, key_id="worker-key")
    result = verify_runtime_receipt_signature(receipt_path, signature_path, public_key)
    assert result["valid"] is True
    assert result["key_id"] == "worker-key"

    receipt_path.write_text(
        receipt_path.read_text().replace(
            '"completed_monotonic_ns": 2', '"completed_monotonic_ns": 3'
        )
    )
    assert (
        verify_runtime_receipt_signature(receipt_path, signature_path, public_key)["valid"] is False
    )
