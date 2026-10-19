"""Dependency-free Refinement/Refresh rollout-manifest reconciliation."""

from __future__ import annotations

import json
import hashlib
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


def check_initial_state(record: dict[str, Any]) -> None:
    """Validate the source's content-addressed numeric state record."""
    require(isinstance(record, dict) and all(key in record for key in ("sha256", "dtype", "shape", "values")), "Missing paired initial-state record/hash")
    require(isinstance(record["sha256"], str) and len(record["sha256"]) == 64 and all(char in "0123456789abcdef" for char in record["sha256"]), "Invalid paired initial-state hash")
    try:
        import numpy as np

        array = np.asarray(record["values"], dtype=record["dtype"])
    except (TypeError, ValueError):
        raise ValueError("Invalid initial-state array") from None
    require(array.dtype.kind in "fiu" and np.isfinite(array).all() and array.size > 0, "Invalid initial-state values")
    require(list(array.shape) == record["shape"], "Initial-state shape mismatch")
    header = json.dumps([array.dtype.str, list(array.shape)], separators=(",", ":")).encode()
    digest = hashlib.sha256(header + array.astype(array.dtype, copy=False).tobytes(order="C")).hexdigest()
    require(digest == record["sha256"], "Initial-state content/hash mismatch")


def reconcile_rollout_journal(root: str | Path, rows: list[dict[str, Any]]) -> None:
    """Recompute retained action/outcome evidence independently of episode totals."""
    events = [json.loads(line) for line in (Path(root) / "steps.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    cursor = 0
    seen: set[str] = set()
    for row in rows:
        run_id = row.get("run_id")
        require(isinstance(run_id, str) and run_id and run_id not in seen, "Missing/duplicate actual attempt ID")
        seen.add(run_id)
        require(cursor < len(events), "Missing episode journal start")
        start = events[cursor]
        require(start.get("kind") == "episode_start" and start.get("run_id") == run_id and start.get("episode_identity") == row["episode_identity"] and start.get("initial_state") == row["initial_state"] and start.get("initial_observation_sha256") == row["initial_observation_sha256"], "Episode journal start differs from completed episode")
        cursor += 1
        actions: list[str] = []
        successes: list[bool] = []
        for tick in range(row["steps"]):
            require(cursor < len(events), "Missing dispatched-action journal record")
            event = events[cursor]
            require(event.get("kind") == "step" and event.get("run_id") == run_id and event.get("tick") == tick, "Action journal order/identity differs")
            generated = tick % row["h"] == 0
            require(type(event.get("new_generation")) is bool and event["new_generation"] == generated and event.get("generation_origin_tick") == tick - tick % row["h"] and event.get("action_age_ticks") == tick % row["h"], "Action generation schedule differs")
            seed = int.from_bytes(bytes.fromhex(canonical_sha(["policy_noise", row["episode_identity"], tick]))[:4], "little")
            require(event.get("noise_seed") == (seed if generated else None), "Dispatched-action noise key differs")
            action = event.get("producer_action")
            check_initial_state(action)
            require(action["shape"] == [7] and action["sha256"] == event.get("environment_action_sha256"), "Producer/consumer action hash differs")
            flags = ("driver_terminated", "driver_truncated", "driver_is_success", "vector_terminated", "vector_truncated", "vector_is_success")
            require(all(type(event.get(key)) is bool for key in flags), "Invalid action-journal outcome flag")
            require(event["driver_terminated"] == event["vector_terminated"] and event["driver_is_success"] == event["vector_is_success"], "Driver/vector outcomes differ")
            require(not event["driver_truncated"] or event["vector_truncated"], "Driver truncation disappeared")
            require(type(event.get("reward")) in (float, int) and event["reward"] == event["reward"] and abs(event["reward"]) != float("inf"), "Invalid step reward")
            require(tick == row["steps"] - 1 or not (event["vector_terminated"] or event["vector_truncated"]), "Action journal continues after episode termination")
            actions.append(action["sha256"])
            successes.append(event["driver_is_success"])
            cursor += 1
        require(any(successes) == row["success"] and canonical_sha(actions) == row.get("action_stream_sha256"), "Action journal and completed outcome/stream digest disagree")
        terminal_event = event
        reason = ("success" if any(successes) else "terminated" if terminal_event["vector_terminated"] else "truncated" if terminal_event["vector_truncated"] else "task_horizon")
        require(row.get("termination_reason") == reason, "Termination reason differs from action journal")
        terminal = {"reward": terminal_event["reward"], "terminated": terminal_event["driver_terminated"], "truncated": terminal_event["driver_truncated"], "is_success": terminal_event["driver_is_success"]}
        require(row["independent_driver"].get("terminal_record") == terminal, "Independent terminal record differs")
        require(cursor < len(events), "Missing episode journal completion")
        end = events[cursor]
        require(end == {"kind": "episode_completed", "run_id": run_id, "success": row["success"], "steps": row["steps"], "action_stream_sha256": row["action_stream_sha256"]}, "Episode journal completion disagrees")
        cursor += 1
    require(cursor == len(events), "Undeclared or partial episode events remain in journal")


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
