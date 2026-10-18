"""Verifiable execution receipts for run and campaign evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


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
    if completed_monotonic_ns < started_monotonic_ns:
        raise ValueError("completed_monotonic_ns must not precede start")
    if not backend_id or not status:
        raise ValueError("backend_id and status are required")
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
    if not isinstance(digest, str):
        return {"valid": False, "reason": "receipt_digest_missing"}
    payload = {key: value for key, value in receipt.items() if key != "receipt_digest_sha256"}
    if _digest(payload) != digest:
        return {"valid": False, "reason": "receipt_digest_mismatch"}
    try:
        started = int(receipt["started_monotonic_ns"])
        completed = int(receipt["completed_monotonic_ns"])
        duration = int(receipt["duration_ns"])
    except (KeyError, TypeError, ValueError):
        return {"valid": False, "reason": "timing_fields_invalid"}
    if completed < started or duration != completed - started:
        return {"valid": False, "reason": "timing_invariant_failed"}
    plan_digest = receipt.get("plan_digest_sha256")
    if plan_digest is not None:
        try:
            _require_sha256(plan_digest, "plan_digest_sha256")
        except ValueError as exc:
            return {"valid": False, "reason": str(exc)}
    required = ("status", "backend_id", "clock_domain", "environment")
    if any(key not in receipt for key in required):
        return {"valid": False, "reason": "required_field_missing"}
    return {"valid": True, "reason": "ok", "receipt_digest_sha256": digest}


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
