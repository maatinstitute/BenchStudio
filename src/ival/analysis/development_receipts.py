"""Fail-closed receipts for non-scientific SmolVLA development checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _require_digest(receipt: dict[str, Any], field: str) -> None:
    if not isinstance(receipt.get(field), str) or not _HEX64.fullmatch(receipt[field]):
        raise ValueError(f"development receipt requires {field} SHA256 identity")


def validate_development_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Validate a zero/one-update receipt that can never close a science cell."""
    if receipt.get("schema_version") != "smolvla_development_receipt_v1":
        raise ValueError("development receipt schema is invalid")
    if receipt.get("status") != "complete" or receipt.get("development_only") is not True:
        raise ValueError("development receipt must remain development-only")
    if (
        receipt.get("science_eligible") is not False
        or receipt.get("checkpoint_eligible") is not False
    ):
        raise ValueError("development receipt cannot be science eligible")
    if receipt.get("checkpoint_discarded") is not True:
        raise ValueError("development checkpoint must be discarded")
    for field in ("base_checkpoint_sha256", "output_sha256"):
        _require_digest(receipt, field)
    kind = receipt.get("kind")
    updates = receipt.get("updates")
    if kind == "zero_update":
        if updates != 0:
            raise ValueError("zero-update development receipt has invalid updates")
        if receipt.get("parameter_delta_max") != 0.0:
            raise ValueError("zero-update check must have zero-update parameter delta")
        if receipt.get("reload_preprocessing_match") is not True:
            raise ValueError("zero-update reload preprocessing check is missing")
        if receipt.get("fixed_noise_action_match") is not True:
            raise ValueError("zero-update fixed-noise action check is missing")
    elif kind == "one_update":
        if updates != 1:
            raise ValueError("one-update development receipt has invalid updates")
        if receipt.get("finite_loss") is not True:
            raise ValueError("one-update check requires finite loss")
        if (
            type(receipt.get("updated_parameter_count")) is not int
            or receipt["updated_parameter_count"] <= 0
        ):
            raise ValueError("one-update check requires updated parameters")
        if (
            receipt.get("mask_valid_positions") != 50
            or receipt.get("mask_reduction_verified") is not True
        ):
            raise ValueError("one-update mask check is missing")
    else:
        raise ValueError("development receipt kind must be zero_update or one_update")
    return receipt


def build_development_receipt(
    kind: str, *, base_checkpoint_sha256: str, output_sha256: str, metrics: dict[str, Any]
) -> dict[str, Any]:
    """Construct a validator-approved development receipt from runtime metrics."""
    if kind not in {"zero_update", "one_update"}:
        raise ValueError("development receipt kind must be zero_update or one_update")
    if not isinstance(metrics, dict):
        raise ValueError("development metrics must be a mapping")
    reserved = {
        "schema_version",
        "status",
        "development_only",
        "science_eligible",
        "checkpoint_eligible",
        "kind",
        "updates",
        "base_checkpoint_sha256",
        "output_sha256",
        "checkpoint_discarded",
    }
    if reserved & set(metrics):
        raise ValueError("development metrics contain reserved receipt fields")
    receipt = {
        "schema_version": "smolvla_development_receipt_v1",
        "status": "complete",
        "development_only": True,
        "science_eligible": False,
        "checkpoint_eligible": False,
        "kind": kind,
        "updates": 0 if kind == "zero_update" else 1,
        "base_checkpoint_sha256": base_checkpoint_sha256,
        "output_sha256": output_sha256,
        "checkpoint_discarded": True,
        **metrics,
    }
    return validate_development_receipt(receipt)


def write_development_receipt(receipt: dict[str, Any], path: str | Path) -> Path:
    """Validate and atomically publish a development-only receipt."""
    validate_development_receipt(receipt)
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    temporary.replace(target)
    return target


def read_development_receipt(path: str | Path) -> dict[str, Any]:
    target = Path(path).resolve()
    receipt = json.loads(target.read_text())
    if not isinstance(receipt, dict):
        raise ValueError("development receipt must be a JSON object")
    return validate_development_receipt(receipt)
