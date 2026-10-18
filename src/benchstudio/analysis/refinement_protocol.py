"""Dependency-free measurement primitives from the Refinement/Refresh runner."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

DEFAULT_CONDITIONS = {(1, 5), (1, 10), (5, 5), (5, 10)}
CONDITIONS = DEFAULT_CONDITIONS
RTOL = 1e-5
ATOL = 1e-6


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
    ).encode("utf-8")


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def require(value: Any, message: str) -> None:
    if not value:
        raise ValueError(message)


def file_sha(path: str | Path) -> str:
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def keyed_seed(identity: Any, tick: int | None = None, domain: str = "policy_noise") -> int:
    key = [domain, identity] if tick is None else [domain, identity, tick]
    return int.from_bytes(hashlib.sha256(canonical(key)).digest()[:4], "little")


def batch_one_success(info: dict[str, Any]) -> bool:
    """Read a single-environment success result through evaluator wrappers."""
    if "final_info" in info:
        final = info["final_info"]
        if isinstance(final, dict):
            return batch_one_success(final)
        if not isinstance(final, (list, tuple)) or len(final) != 1 or final[0] is None:
            raise ValueError("invalid batch-one final_info")
        return batch_one_success(final[0])
    if "is_success" not in info:
        raise ValueError("environment success field missing")
    value = info["is_success"]
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise ValueError("success info must be batch one")
        value = value[0]
    return bool(value)


def development_schedule() -> list[dict[str, Any]]:
    identity = {
        "suite": "libero_spatial",
        "task_id": 0,
        "initial_state_id": 0,
        "policy_seed": 1000,
    }
    block_id = "development.libero_spatial.task000.state000.seed1000"
    return [
        {
            "schedule_index": index,
            "block_index": 0,
            "condition_index": index,
            "block_id": block_id,
            "episode_identity": identity.copy(),
            "condition_id": f"h{h}_d{d}",
            "planned_run_id": f"{block_id}.h{h}_d{d}",
            "h": h,
            "denoising_steps": d,
            "native_reference": (h, d) == (1, 10),
        }
        for index, (h, d) in enumerate(((1, 10), (5, 5), (1, 5), (5, 10)))
    ]


def select_schedule(plan: dict[str, Any], max_blocks: int | None = None) -> list[dict[str, Any]]:
    """Select complete, balanced state/seed pairs before outcomes exist.

    This is the source runner's ``select_schedule`` contract. It validates
    the frozen schedule digest and condition blocks, then optionally selects
    whole blocks equally per task while retaining every declared policy seed.
    """
    rows = plan["schedule"]
    if not rows or sha(rows) != plan["scheduling"]["schedule_sha256"]:
        raise ValueError("plan schedule digest missing or incorrect")
    declared = plan.get("design", {}).get("conditions")
    if not isinstance(declared, list) or not declared:
        raise ValueError("plan must declare nonempty conditions")
    conditions = {(row.get("h"), row.get("denoising_steps")) for row in declared}
    if not all(
        type(h) is int and h > 0 and type(denoising_steps) is int and denoising_steps > 0
        for h, denoising_steps in conditions
    ):
        raise ValueError("h and denoising_steps must be positive integers")
    if len(conditions) != len(declared):
        raise ValueError("duplicate declared conditions")
    per_block = len(conditions)
    if plan["design"].get("conditions_per_block") != per_block:
        raise ValueError("conditions_per_block disagrees with declared conditions")
    blocks: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for row in rows:
        block_id = row["block_id"]
        if block_id not in blocks:
            blocks[block_id] = []
            order.append(block_id)
        blocks[block_id].append(row)
    for block_id, block in blocks.items():
        if (
            len(block) != per_block
            or {(row["h"], row["denoising_steps"]) for row in block} != conditions
        ):
            raise ValueError(
                f"incomplete or mismatched condition block {block_id} "
                "(historical four-condition or declared grid)"
            )
        if not all(row["episode_identity"] == block[0]["episode_identity"] for row in block):
            raise ValueError(f"mixed identities in block {block_id}")
    if [row["block_id"] for row in rows] != [
        block_id for block_id in order for _ in range(per_block)
    ]:
        raise ValueError("condition blocks must be contiguous")
    if len({row["planned_run_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate planned_run_id")
    if max_blocks is None:
        return copy.deepcopy(rows)
    if type(max_blocks) is not int or not 0 < max_blocks <= len(blocks):
        raise ValueError("invalid max-blocks")
    if max_blocks == len(blocks):
        return copy.deepcopy(rows)
    task_states: dict[tuple[Any, Any], dict[Any, list[str]]] = {}
    for block_id in order:
        identity = blocks[block_id][0]["episode_identity"]
        task = (identity["suite"], identity["task_id"])
        task_states.setdefault(task, {}).setdefault(identity["initial_state_id"], []).append(
            block_id
        )
    seeds = set(plan["design"]["policy_seeds"])
    divisor = len(task_states) * len(seeds)
    if max_blocks % divisor != 0:
        raise ValueError(
            f"--max-blocks must be a multiple of {divisor} to preserve task/state/seed balance"
        )
    states_per_task = max_blocks // divisor
    selected: set[str] = set()
    for task, states in task_states.items():
        if len(states) < states_per_task:
            raise ValueError(f"not enough states for {task}")
        for _state, block_ids in list(states.items())[:states_per_task]:
            actual = {
                blocks[block_id][0]["episode_identity"]["policy_seed"] for block_id in block_ids
            }
            if actual != seeds or len(block_ids) != len(seeds):
                raise ValueError("incomplete policy-seed pair")
            selected.update(block_ids)
    selected_rows = [row for row in rows if row["block_id"] in selected]
    if len(selected_rows) != max_blocks * per_block:
        raise ValueError("balanced selection size mismatch")
    return copy.deepcopy(selected_rows)


def compare_arrays(
    reference: Any, candidate: Any, rtol: float = RTOL, atol: float = ATOL
) -> dict[str, Any]:
    """Compare finite arrays using the source development-gate contract."""
    import numpy as np

    left, right = np.asarray(reference), np.asarray(candidate)
    require(
        left.shape == right.shape and np.isfinite(left).all() and np.isfinite(right).all(),
        "comparison requires finite arrays with identical shapes",
    )
    delta = np.abs(left.astype(np.float64) - right.astype(np.float64))
    return {
        "exact_equal": bool(np.array_equal(left, right)),
        "allclose": bool(np.allclose(left, right, rtol=rtol, atol=atol)),
        "max_abs_diff": float(delta.max()),
        "mean_abs_diff": float(delta.mean()),
        "rtol": rtol,
        "atol": atol,
    }


def profiler_counts(profiler: Any, methods: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Count original method code identities, not ambiguous function names."""
    import inspect
    import pstats

    stats = pstats.Stats(profiler).stats
    result: dict[str, dict[str, Any]] = {}
    for label, method in methods.items():
        code = inspect.unwrap(method).__code__
        key = (code.co_filename, code.co_firstlineno, code.co_name)
        primitive, total, _own_s, _cumulative_s, _callers = stats.get(key, (0, 0, 0.0, 0.0, {}))
        result[label] = {
            "primitive_calls": primitive,
            "total_calls": total,
            "source_file": code.co_filename,
            "first_line": code.co_firstlineno,
            "function": code.co_name,
        }
    return result


def image_variants(observation: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Create native, camera-swapped, and zero-image development inputs."""
    import numpy as np

    require(isinstance(observation.get("pixels"), dict), "raw pixels dictionary required")
    keys = sorted(observation["pixels"])
    require(len(keys) == 2, "exactly two real camera inputs required")
    a, b = (np.asarray(observation["pixels"][key]) for key in keys)
    require(a.shape == b.shape and a.dtype == b.dtype, "camera swap requires matching arrays")
    require(not np.array_equal(a, b), "camera images unexpectedly identical")
    swap, zero = copy.deepcopy(observation), copy.deepcopy(observation)
    swap["pixels"][keys[0]], swap["pixels"][keys[1]] = b.copy(), a.copy()
    for key in keys:
        zero["pixels"][key] = np.zeros_like(observation["pixels"][key])
    return {"native": copy.deepcopy(observation), "camera_swap": swap, "zero_images": zero}, keys


def array_record(value: Any) -> dict[str, Any]:
    import numpy as np

    array = np.ascontiguousarray(np.asarray(value))
    if array.dtype.kind not in "fiu" or not np.isfinite(array).all():
        raise ValueError("nonfinite/non-numeric array")
    header = json.dumps([array.dtype.str, list(array.shape)], separators=(",", ":")).encode()
    return {
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "values": array.tolist(),
        "sha256": hashlib.sha256(header + array.tobytes()).hexdigest(),
    }


def observation_sha(observation: Any) -> str:
    import numpy as np

    def encode(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: encode(item) for key, item in sorted(value.items())}
        if isinstance(value, np.ndarray):
            return array_record(value)["sha256"]
        return value

    return sha(encode(observation))


def observation_field_shas(observation: Any) -> Any:
    """Return compact recursive hashes for audit logs without storing inputs."""
    import numpy as np

    if isinstance(observation, dict):
        return {key: observation_field_shas(value) for key, value in sorted(observation.items())}
    if isinstance(observation, np.ndarray):
        return array_record(observation)["sha256"]
    return sha(observation)


def json_line(stream: Any, value: Any) -> None:
    stream.write(json.dumps(value, allow_nan=False, default=str) + "\n")
    stream.flush()


def parity_report(
    reference: dict[str, Any],
    initial_state: dict[str, Any],
    initial_observation_sha256: str,
    actions: Iterable[Any],
    success: bool,
) -> dict[str, Any]:
    action_records = [array_record(action) for action in actions]
    stream_digest = sha([record["sha256"] for record in action_records])
    checks = {
        "initial_state_equal": initial_state["sha256"] == reference["initial_state"]["sha256"],
        "initial_observation_equal": (
            initial_observation_sha256 == reference["initial_observation_sha256"]
        ),
        "action_stream_exact": stream_digest == reference["action_stream_sha256"],
        "episode_steps_equal": len(action_records) == reference["steps"],
        "success_equal": bool(success) == reference["success"],
    }
    return {
        "schema_version": 1,
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "reference_run_id": reference["run_id"],
        "episode_identity": reference["episode_identity"],
        "h": reference["h"],
        "denoising_steps": reference["denoising_steps"],
        "upstream_steps": len(action_records),
        "upstream_success": bool(success),
        "upstream_initial_state": initial_state,
        "upstream_initial_observation_sha256": initial_observation_sha256,
        "upstream_action_stream_sha256": stream_digest,
        "upstream_actions": action_records,
        "scope": (
            "Pinned upstream rollout loop with same explicit tick-keyed noise and state; "
            "does not assert the stock global-RNG trajectory is identical."
        ),
    }
