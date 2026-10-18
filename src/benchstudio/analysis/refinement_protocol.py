"""Dependency-free measurement primitives from the Refinement/Refresh runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

DEFAULT_CONDITIONS = {(1, 5), (1, 10), (5, 5), (5, 10)}
CONDITIONS = DEFAULT_CONDITIONS


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
    ).encode("utf-8")


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


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
