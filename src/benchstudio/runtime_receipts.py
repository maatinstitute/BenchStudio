"""Verifiable execution receipts for run and campaign evidence."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from .evidence import sha256_file


def build_runtime_receipt(
    *,
    run_id: str | None,
    attempt_id: str | None,
    plan_digest_sha256: str | None,
    worker_id: str | None,
    status: str,
    started_monotonic_ns: int,
    completed_monotonic_ns: int,
    backend_id: str,
    environment: dict[str, Any],
) -> dict[str, Any]:
    """Build a self-contained receipt without hashing itself recursively."""
    if not isinstance(started_monotonic_ns, int) or isinstance(started_monotonic_ns, bool):
        raise ValueError("started_monotonic_ns must be an integer")
    if not isinstance(completed_monotonic_ns, int) or isinstance(completed_monotonic_ns, bool):
        raise ValueError("completed_monotonic_ns must be an integer")
    if not isinstance(status, str) or not status:
        raise ValueError("status must be a non-empty string")
    if not isinstance(backend_id, str) or not backend_id:
        raise ValueError("backend_id must be a non-empty string")
    if not isinstance(environment, dict):
        raise ValueError("environment must be a mapping")
    if completed_monotonic_ns < started_monotonic_ns:
        raise ValueError("completed_monotonic_ns must not precede start")
    if plan_digest_sha256 is not None:
        _require_sha256(plan_digest_sha256, "plan_digest_sha256")
    payload = {
        "schema": "benchstudio_runtime_receipt_v1",
        "run_id": run_id,
        "attempt_id": attempt_id,
        "plan_digest_sha256": plan_digest_sha256,
        "worker_id": worker_id,
        "status": status,
        "clock_domain": "host_monotonic",
        "started_monotonic_ns": started_monotonic_ns,
        "completed_monotonic_ns": completed_monotonic_ns,
        "duration_ns": completed_monotonic_ns - started_monotonic_ns,
        "backend_id": backend_id,
        "environment": dict(environment),
    }
    return {**payload, "receipt_digest_sha256": _digest(payload)}


def write_runtime_receipt(path: Path, receipt: dict[str, Any]) -> None:
    """Validate and write a canonical receipt."""
    verification = verify_runtime_receipt(receipt)
    if not verification["valid"]:
        raise ValueError(f"invalid runtime receipt: {verification['reason']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_runtime_receipt(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("runtime receipt is unreadable") from exc


def verify_runtime_receipt(receipt: dict[str, Any] | Path) -> dict[str, Any]:
    """Verify schema, timing invariants, and the receipt's content digest."""
    if isinstance(receipt, Path):
        try:
            receipt = load_runtime_receipt(receipt)
        except ValueError as exc:
            return {"valid": False, "reason": str(exc)}
    if not isinstance(receipt, dict):
        return {"valid": False, "reason": "receipt_not_mapping"}
    if receipt.get("schema") != "benchstudio_runtime_receipt_v1":
        return {"valid": False, "reason": "schema_mismatch"}
    digest = receipt.get("receipt_digest_sha256")
    if not isinstance(digest, str) or not _is_hex_digest(digest):
        return {"valid": False, "reason": "receipt_digest_missing"}
    payload = {key: value for key, value in receipt.items() if key != "receipt_digest_sha256"}
    try:
        payload_digest = _digest(payload)
    except (TypeError, ValueError):
        return {"valid": False, "reason": "receipt_content_invalid"}
    if payload_digest != digest:
        return {"valid": False, "reason": "receipt_digest_mismatch"}
    required = ("status", "backend_id", "clock_domain", "environment")
    if any(key not in receipt for key in required):
        return {"valid": False, "reason": "required_field_missing"}
    if (
        not isinstance(receipt["status"], str)
        or not receipt["status"]
        or not isinstance(receipt["backend_id"], str)
        or not receipt["backend_id"]
        or receipt["clock_domain"] != "host_monotonic"
        or not isinstance(receipt["environment"], dict)
    ):
        return {"valid": False, "reason": "receipt_fields_invalid"}
    for field in ("run_id", "attempt_id", "plan_digest_sha256", "worker_id"):
        value = receipt.get(field)
        if value is not None and not isinstance(value, str):
            return {"valid": False, "reason": f"{field}_invalid"}
    try:
        started = receipt["started_monotonic_ns"]
        completed = receipt["completed_monotonic_ns"]
        duration = receipt["duration_ns"]
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in (started, completed, duration)
        ):
            raise TypeError
    except (KeyError, TypeError):
        return {"valid": False, "reason": "timing_fields_invalid"}
    if completed < started or duration != completed - started:
        return {"valid": False, "reason": "timing_invariant_failed"}
    plan_digest = receipt.get("plan_digest_sha256")
    if plan_digest is not None:
        try:
            _require_sha256(plan_digest, "plan_digest_sha256")
        except ValueError as exc:
            return {"valid": False, "reason": str(exc)}
    return {"valid": True, "reason": "ok", "receipt_digest_sha256": digest}


def sign_runtime_receipt(
    receipt_path: Path,
    private_key_pem: bytes,
    signature_path: Path,
    *,
    key_id: str | None = None,
) -> dict[str, Any]:
    """Write a detached Ed25519 signature over a runtime receipt file."""
    from .evidence_signing import _crypto

    serialization, _ = _crypto()
    receipt = load_runtime_receipt(receipt_path)
    verification = verify_runtime_receipt(receipt)
    if not verification["valid"]:
        raise ValueError(f"cannot sign invalid runtime receipt: {verification['reason']}")
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    receipt_sha256 = sha256_file(receipt_path)
    signature = private_key.sign(_receipt_signature_payload(receipt_sha256))
    record: dict[str, Any] = {
        "schema": "benchstudio_runtime_receipt_signature_v1",
        "algorithm": "ed25519",
        "receipt_sha256": receipt_sha256,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }
    if key_id is not None:
        if not key_id:
            raise ValueError("key_id must not be empty")
        record["key_id"] = key_id
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    signature_path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return record


def verify_runtime_receipt_signature(
    receipt_path: Path,
    signature_path: Path,
    public_key_pem: bytes,
) -> dict[str, Any]:
    """Verify a detached receipt signature against an external public key."""
    from .evidence_signing import _crypto

    serialization, _ = _crypto()
    try:
        record = json.loads(signature_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"valid": False, "reason": f"signature_read_error: {exc}"}
    receipt_verification = verify_runtime_receipt(receipt_path)
    if not receipt_verification["valid"]:
        return {"valid": False, "reason": "runtime_receipt_invalid"}
    actual_digest = sha256_file(receipt_path)
    if record.get("schema") != "benchstudio_runtime_receipt_signature_v1":
        return {"valid": False, "reason": "signature_schema_mismatch"}
    if record.get("algorithm") != "ed25519":
        return {"valid": False, "reason": "signature_algorithm_mismatch"}
    if record.get("receipt_sha256") != actual_digest:
        return {"valid": False, "reason": "signed_receipt_digest_mismatch"}
    try:
        signature = base64.b64decode(record["signature_base64"], validate=True)
        public_key = serialization.load_pem_public_key(public_key_pem)
        public_key.verify(signature, _receipt_signature_payload(actual_digest))
    except Exception as exc:
        return {"valid": False, "reason": f"signature_verification_failed: {type(exc).__name__}"}
    result: dict[str, Any] = {
        "valid": True,
        "algorithm": record["algorithm"],
        "receipt_sha256": actual_digest,
    }
    if "key_id" in record:
        result["key_id"] = record["key_id"]
    return result


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _require_sha256(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


def _is_hex_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _receipt_signature_payload(receipt_sha256: str) -> bytes:
    return json.dumps(
        {
            "schema": "benchstudio_runtime_receipt_signature_v1",
            "receipt_sha256": receipt_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
