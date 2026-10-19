"""Dependency-free Refinement/Refresh rollout-manifest reconciliation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .refinement_query_recovery import canonical_sha


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def episode_key(row: dict[str, Any]) -> tuple[str, int, int, int]:
    identity = row.get("episode_identity", {})
    require(isinstance(identity, dict) and isinstance(identity.get("suite"), str) and identity["suite"], "Missing/invalid episode identity")
    require(all(type(identity.get(key)) is int and identity[key] >= 0 for key in ("task_id", "initial_state_id", "policy_seed")), "Invalid state/task/seed identity")
    return (identity["suite"], identity["task_id"], identity["initial_state_id"], identity["policy_seed"])


def reconcile_rollout_manifest(root: str | Path, completion: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Ensure completed rows match the declared schedule, not just each other."""
    root_path = Path(root)
    runtime_path = root_path / "runtime_manifest.json"
    require(runtime_path.is_file(), "Missing declared runtime/schedule manifest")
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime_hash = canonical_sha(runtime)
    require(completion.get("runtime_manifest_sha256") == runtime_hash, "Runtime manifest digest disagrees with completed summary")
    schedule = runtime.get("selected_schedule")
    require(isinstance(schedule, list) and schedule, "Missing declared selected schedule")
    schedule_hash = canonical_sha(schedule)
    require(runtime.get("selected_schedule_sha256") == schedule_hash and completion.get("schedule_sha256") == schedule_hash, "Declared schedule hash mismatch")
    expected: dict[tuple[tuple[str, int, int, int], tuple[Any, Any]], dict[str, Any]] = {}
    for row in schedule:
        key = (episode_key(row), (row.get("h"), row.get("denoising_steps")))
        require(key not in expected, "Duplicate identity/condition in declared schedule")
        expected[key] = row
    actual: dict[tuple[tuple[str, int, int, int], tuple[Any, Any]], dict[str, Any]] = {}
    for row in rows:
        key = (episode_key(row), (row.get("h"), row.get("denoising_steps")))
        require(key not in actual, "Duplicate completed identity/condition")
        require(key in expected and all(row.get(field) == expected[key].get(field) for field in ("planned_run_id", "block_id")), "Completed row differs from selected schedule")
        require(row.get("runtime_manifest_sha256") == runtime_hash, "Episode/runtime manifest hash mismatch")
        actual[key] = row
    require(set(actual) == set(expected), "Missing declared paired cells/blocks")
    require(all(type(completion.get(field)) is int and completion[field] == len(rows) for field in ("completed_attempts", "expected_attempts")), "Completed/expected attempt totals disagree")
    require(completion.get("completed_blocks") == len({row["block_id"] for row in rows}), "Completed block total disagrees")
    require(completion.get("episodes") == rows, "Completed summary and episode journal disagree")
    require(completion.get("aggregate_successes") == sum(row.get("success") is True for row in rows), "Completed aggregate success count disagrees")
    return runtime
