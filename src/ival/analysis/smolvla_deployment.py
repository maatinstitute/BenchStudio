"""Validation of archived external SmolVLA deployment evidence.

This module verifies summary arithmetic and pinned runtime identities. It does
not load weights, execute LeRobot, or turn aggregate evidence into a stronger
pairing or benchmark claim than the archive declares.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def load_smolvla_deployment_evidence(
    manifest_path: str | Path,
    summary_path: str | Path,
    *,
    expected_manifest_sha256: str | None = None,
    expected_summary_sha256: str | None = None,
) -> dict[str, Any]:
    """Load and validate an archived SmolVLA deployment manifest and summary."""
    manifest_path = Path(manifest_path)
    summary_path = Path(summary_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _invalid(f"{type(exc).__name__}: {exc}")
    issues = _validate_manifest(manifest)
    rows: list[dict[str, Any]] = []
    if not isinstance(summary, list) or not summary:
        issues.append("summary must be a non-empty array")
    else:
        for index, row in enumerate(summary):
            row_issues = _validate_row(row)
            if row_issues:
                issues.extend(f"summary[{index}]: {issue}" for issue in row_issues)
            elif isinstance(row, dict):
                rows.append(dict(row))
    manifest_sha256 = _sha256(manifest_path)
    summary_sha256 = _sha256(summary_path)
    issues.extend(
        _check_expected_digest(
            "manifest_sha256", expected_manifest_sha256, manifest_sha256
        )
    )
    issues.extend(
        _check_expected_digest("summary_sha256", expected_summary_sha256, summary_sha256)
    )
    return {
        "schema": "ival.smolvla_deployment_evidence.v1",
        "valid": not issues,
        "issues": issues,
        "manifest": manifest if isinstance(manifest, dict) else None,
        "summary": rows,
        "manifest_sha256": manifest_sha256,
        "summary_sha256": summary_sha256,
        "execution_status": "archived_external_evidence",
        "weights_and_runtime": "external",
    }


def _validate_manifest(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["manifest must be an object"]
    required = {
        "checkpoint",
        "checkpoint_revision",
        "lerobot_revision",
        "environment",
        "task_ids_primary",
        "suite_gate",
        "seed",
        "primary_episodes",
        "denoising_steps_primary",
        "device",
        "ledger_version",
        "instrumentation",
        "timing_limitations",
        "pairing_status",
        "scope",
    }
    issues = [f"missing field: {key}" for key in sorted(required - set(value))]
    for key in ("checkpoint_revision", "lerobot_revision"):
        revision = value.get(key)
        if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
            issues.append(f"{key} must be a lowercase 40-character commit identity")
    for key in (
        "checkpoint",
        "environment",
        "device",
        "timing_limitations",
        "pairing_status",
        "scope",
    ):
        if not isinstance(value.get(key), str) or not value[key]:
            issues.append(f"{key} must be a non-empty string")
    for key in ("seed", "primary_episodes", "denoising_steps_primary", "ledger_version"):
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            issues.append(f"{key} must be a positive integer")
    task_ids = value.get("task_ids_primary")
    if (
        not isinstance(task_ids, list)
        or not task_ids
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in task_ids)
    ):
        issues.append("task_ids_primary must be a non-empty list of non-negative integers")
    suite_gate = value.get("suite_gate")
    if not isinstance(suite_gate, dict) or not suite_gate:
        issues.append("suite_gate must be a non-empty object")
    elif any(
        not isinstance(key, str)
        or not key
        or isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or rate < 0
        or rate > 1
        for key, rate in suite_gate.items()
    ):
        issues.append("suite_gate values must be finite rates in [0, 1]")
    instrumentation = value.get("instrumentation")
    if (
        not isinstance(instrumentation, list)
        or not instrumentation
        or any(not isinstance(item, str) or not item for item in instrumentation)
    ):
        issues.append("instrumentation must be a non-empty list of strings")
    return issues


def _validate_row(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["row must be an object"]
    issues: list[str] = []
    positive_ints = ("n_action_steps", "control_steps", "neural_chunk_calls")
    for key in positive_ints:
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            issues.append(f"{key} must be a positive integer")
    successes = value.get("successes")
    if (
        not isinstance(successes, list)
        or not successes
        or any(type(item) is not bool for item in successes)
    ):
        issues.append("successes must be a non-empty list of booleans")
    for key in (
        "control_to_neural",
        "success_rate_percent",
        "eval_seconds",
        "neural_p50_seconds",
        "neural_p95_seconds",
    ):
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            issues.append(f"{key} must be finite numeric")
    if not issues:
        control_steps = value["control_steps"]
        neural_calls = value["neural_chunk_calls"]
        expected_ratio = control_steps / neural_calls
        if not math.isclose(value["control_to_neural"], expected_ratio, rel_tol=1e-9, abs_tol=1e-9):
            issues.append("control_to_neural does not match control_steps/neural_chunk_calls")
        expected_rate = 100.0 * sum(value["successes"]) / len(value["successes"])
        if not math.isclose(
            value["success_rate_percent"], expected_rate, rel_tol=1e-9, abs_tol=1e-9
        ):
            issues.append("success_rate_percent does not match successes")
        if (
            value["eval_seconds"] <= 0
            or value["neural_p50_seconds"] < 0
            or value["neural_p95_seconds"] < 0
        ):
            issues.append("timing values must be non-negative and eval_seconds positive")
        if value["neural_p95_seconds"] < value["neural_p50_seconds"]:
            issues.append("neural_p95_seconds must be at least neural_p50_seconds")
    return issues


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _check_expected_digest(
    field: str, expected: str | None, actual: str | None
) -> list[str]:
    if expected is None:
        return []
    if not isinstance(expected, str) or not _DIGEST_RE.fullmatch(expected):
        return [f"{field} expectation must be a lowercase 64-character SHA-256 digest"]
    if actual != expected:
        return [f"{field} does not match the independently supplied digest"]
    return []


def _invalid(issue: str) -> dict[str, Any]:
    return {
        "schema": "ival.smolvla_deployment_evidence.v1",
        "valid": False,
        "issues": [issue],
        "manifest": None,
        "summary": [],
        "manifest_sha256": None,
        "summary_sha256": None,
        "execution_status": "archived_external_evidence",
        "weights_and_runtime": "external",
    }
