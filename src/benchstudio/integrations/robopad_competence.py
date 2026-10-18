"""RoboPAD competence/replay evidence helpers; no policy or simulator authority."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

MAX_BYTES = 100_000_000


def sha(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scalar(value: Any) -> Any:
    import numpy as np

    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def persist(path: Path, value: dict[str, Any], *, array: bool = False) -> None:
    """Serialize before writing while enforcing the source byte ceiling."""
    import numpy as np

    if array:
        stream = io.BytesIO()
        np.savez_compressed(stream, **value)
        blob = stream.getvalue()
    else:
        blob = (json.dumps(value, indent=2, default=scalar) + "\n").encode()
    root = path.parent
    while root.name != "results" and root != root.parent:
        root = root.parent
    used = sum(item.stat().st_size for item in root.rglob("*") if item.is_file())
    old = path.stat().st_size if path.exists() else 0
    ceiling = (
        MAX_BYTES
        if path.name == "report.json"
        else (90_000_000 if path.name.startswith("frame-") else MAX_BYTES - 1_000_000)
    )
    if used - old + len(blob) > ceiling:
        raise RuntimeError("data ceiling before write")
    path.write_bytes(blob)


def termination(sample: dict[str, Any], done: bool, count: int, limit: int) -> str | None:
    """Classify a RoboPAD exposed-source rollout without inventing success."""
    if not bool(sample["native_success_available"]):
        return "native_success_unavailable"
    if bool(sample["native_success"]):
        return "native_success"
    if done:
        return "environment_done_without_success"
    if count >= min(200, limit):
        return "fixed_duration_exhausted"
    return None


def replay_equal(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Compare replay evidence, including frames and contacts, exactly."""
    import numpy as np

    if first["termination"] != second["termination"]:
        return False
    if first.get("error") or second.get("error"):
        return False
    left, right = first["trace"], second["trace"]
    return (
        left.keys() == right.keys()
        and all(np.array_equal(left[key], right[key]) for key in left)
        and first.get("frame_hashes") == second.get("frame_hashes")
        and first.get("contacts") == second.get("contacts")
    )


def world_rotation_delta(current: Any, desired: Any):
    """Compute the pinned left-multiplicative world rotation delta."""
    import numpy as np

    from ..conformance.path_geometry import proper_rotation

    relative = proper_rotation(desired) @ proper_rotation(current).T
    angle = float(np.arccos(np.clip((np.trace(relative) - 1) / 2, -1, 1)))
    skew = np.array(
        [
            relative[2, 1] - relative[1, 2],
            relative[0, 2] - relative[2, 0],
            relative[1, 0] - relative[0, 1],
        ]
    )
    if angle < 1e-7:
        return skew / 2
    if np.pi - angle < 1e-6:
        _, vectors = np.linalg.eigh((relative + relative.T + 2 * np.eye(3)) / 4)
        axis = vectors[:, -1]
        if np.dot(axis, skew) < 0:
            axis = -axis
        return angle * axis
    return angle * skew / (2 * np.sin(angle))


def checked_rotation_delta(current: Any, desired: Any, retained_goal: Any):
    """Reject a zero command that would silently retain a stale orientation goal."""
    import numpy as np

    delta = world_rotation_delta(current, desired)
    if not np.any(delta) and not np.allclose(retained_goal, desired, atol=1e-8, rtol=0):
        raise ValueError("zero rotation command would retain a stale orientation goal")
    return delta


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    """Remove bulky detail fields from a final summary while preserving hashes."""
    return {
        key: value
        for key, value in record.items()
        if key
        not in (
            "physics_contacts",
            "positions",
            "orientations",
            "controller",
            "stages",
            "frame_hashes",
        )
    }
