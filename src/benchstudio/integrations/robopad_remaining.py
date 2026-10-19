"""RoboPAD remaining-reference scope and exact frame-retention helpers."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

MAX_BYTES = 1_000_000_000


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scalar(value: Any) -> Any:
    import numpy as np

    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def persist(path: Path, value: Any, *, array: bool = False) -> None:
    """Serialize one retained record under the source's bounded data ceiling."""
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
        else (MAX_BYTES - 10_000_000 if path.name.startswith("frame-") else MAX_BYTES - 1_000_000)
    )
    if used - old + len(blob) > ceiling:
        raise RuntimeError("data ceiling before write")
    path.write_bytes(blob)


def remaining_worlds(task: int, demo: int, retry: int) -> list[str]:
    """Return the fixed world scope; no retry or first-parent H/D rerun."""
    if type(task) is not int or type(demo) is not int or task not in (0, 1, 2) or demo not in (0, 1):
        raise ValueError("only six exposed development parents permitted")
    if type(retry) is not int or retry != 0:
        raise ValueError("no retries permitted")
    return ["I"] if (task, demo) == (0, 0) else ["H", "D", "I"]


def retain_frame(directory: Path, step: int, original: dict[str, Any], aligned: dict[str, Any]) -> str:
    """Retain original and independently aligned RGB frames and return their digest."""
    images = {
        prefix + key: sample[key]
        for prefix, sample in (("original_", original), ("physics_", aligned))
        for key in ("rgb_0", "rgb_1")
    }
    frame = Path(directory) / f"frame-{step:03d}.npz"
    persist(frame, images, array=True)
    return sha(frame)
