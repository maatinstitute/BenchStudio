"""RoboPAD fixed development slots and hash-bound source-attempt loading."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PARENTS = tuple((task, demo) for task in range(3) for demo in range(2))
CONTROLLERS = ("vla", "reference", "insensitive")
CELLS = ("HH", "HD", "DH", "DD", "II")
HORIZONS = (1, 5, 10, 20)
CONSUMED = frozenset(
    (0, 0, "vla", cell, horizon)
    for horizon, cell in (
        (1, "HH"),
        (5, "HH"),
        (10, "HH"),
        (20, "HH"),
        (5, "HD"),
        (5, "DH"),
        (5, "DD"),
    )
)


def all_slots() -> tuple[tuple[int, int, str, str, int], ...]:
    return tuple(
        (task, demo, controller, cell, horizon)
        for task, demo in PARENTS
        for controller in CONTROLLERS
        for cell in CELLS
        for horizon in HORIZONS
    )


def remaining_slots() -> tuple[tuple[int, int, str, str, int], ...]:
    return tuple(slot for slot in all_slots() if slot not in CONSUMED)


def suffix_seed(task: int, demo: int, absolute_step: int) -> int:
    if (
        type(task) is not int
        or type(demo) is not int
        or (task, demo) not in PARENTS
        or type(absolute_step) is not int
        or not 0 <= absolute_step <= 200
    ):
        raise ValueError("fixed parent and absolute action count 0..200 required")
    return 7_140_000 + (2 * task + demo) * 1000 + absolute_step


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path, digest: str) -> dict[str, Any]:
    if not isinstance(digest, str) or len(digest) != 64 or sha(path) != digest:
        raise ValueError("provenance hash mismatch: " + str(path))
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON mapping: " + str(path))
    return value


def load_reference_attempt(
    directory: Path,
    *,
    source_manifest: Path,
    source_manifest_sha256: str,
    report_path: Path,
    report_sha256: str,
    task: int,
    demo: int,
    world: str,
):
    """Load one fully recorded source attempt, including native failures.

    Trusted expected hashes must come from the reviewed allocation; this
    function never derives trust from whichever records happen to be present.
    """
    if (
        type(task) is not int
        or type(demo) is not int
        or (task, demo) not in PARENTS
        or world not in ("H", "D", "I")
    ):
        raise ValueError("invalid source identity")
    directory = Path(directory)
    report_path = Path(report_path)
    if (
        directory.name != world + "_attempt"
        or directory.parent.resolve() != report_path.parent.resolve()
    ):
        raise ValueError("only the named attempt beneath the supplied report is permitted")
    source = _read(Path(source_manifest), source_manifest_sha256)
    identity = str(source.get("task_id", "")).split("/")
    if (
        len(identity) < 2
        or identity[0] != "libero_object"
        or identity[1] != str(task)
        or source.get("demo_id") != f"demo_{demo}"
    ):
        raise ValueError("source manifest parent mismatch")
    report = _read(report_path, report_sha256)
    pin = report.get("source_pin", {})
    if (
        pin.get("task") != task
        or pin.get("demo") != demo
        or pin.get("sha256") != source_manifest_sha256
    ):
        raise ValueError("report source identity/hash mismatch")
    if report.get("training") is not False or report.get("policy_loaded") is not False:
        raise ValueError("expected scripted reference report")
    rows = [row for row in report.get("rows", []) if row.get("id") == world + "_attempt"]
    if len(rows) != 1:
        raise ValueError("exactly one source attempt required")
    row = rows[0]
    detail = _read(directory / "record.json", row.get("detail_record_sha256"))
    if detail.get("id") != world + "_attempt" or detail.get("error") or row.get("error"):
        raise ValueError("attempt identity or infrastructure error")
    allowed = ("native_success", "fixed_duration_exhausted", "environment_done_without_success")
    if detail.get("termination") not in allowed or row.get("termination") != detail["termination"]:
        raise ValueError("incomplete/unknown source termination")
    path = directory / "trace.npz"
    if sha(path) != detail.get("trace_sha256") or detail.get("trace_sha256") != row.get(
        "trace_sha256"
    ):
        raise ValueError("trace provenance mismatch")
    import numpy as np

    with np.load(path, allow_pickle=False) as arrays:
        executed = arrays["executed_actions"].copy()
        commanded = arrays["commanded_actions"].copy()
        count = len(executed)
        if any(
            type(record.get(key)) is not int or record[key] != count
            for record in (row, detail)
            for key in ("executed_actions", "commanded_actions")
        ):
            raise ValueError("source action count mismatch")
        if not 0 < count <= 200 or not np.array_equal(executed, commanded):
            raise ValueError("source execution unresolved")
        if detail["termination"] == "fixed_duration_exhausted" and count != (
            156 if world == "D" else 103
        ):
            raise ValueError("fixed source duration mismatch")
        states = arrays["original_states"]
        available = arrays["original_native_success_available"]
        success = arrays["original_native_success"]
        if (
            len(states) != count + 1
            or len(available) != count + 1
            or len(success) != count + 1
            or not np.isfinite(states).all()
            or not np.all(available)
        ):
            raise ValueError("source boundary evidence incomplete")
        if np.any(success[:-1]) or bool(success[-1]) != (detail["termination"] == "native_success"):
            raise ValueError("source native termination inconsistent")
    from ..integrations.robopad_reference_cache import cache_executed_source

    return cache_executed_source(world, executed, row["detail_record_sha256"])
