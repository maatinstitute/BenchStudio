"""RoboPAD's immutable fixed-reference batch reservation and dispatch controls."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

NAMES = tuple(f"task-{task}-demo-{demo}" for task in range(3) for demo in range(2))
FILES = (
    "icra_reference_remaining.py",
    "icra_reference_competence.py",
    "icra_reference.py",
    "icra_reference_pose.py",
    "icra_reference_adapter.py",
    "child.json",
    "parents.json",
    "physical_I_gate.json",
    "launch_pins.json",
)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slots(name: str) -> list[str]:
    worlds = ["I"] if name == NAMES[0] else ["H", "D", "I"]
    return [name + "-" + world + "-" + role for world in worlds for role in ("attempt", "replay")]


def reserve(claims: Path, names: tuple[str, ...], owner: str, reserved: list[str]) -> None:
    """Preflight all claims, then create exclusive claims without rollback."""
    claims.mkdir(parents=True, exist_ok=True)
    desired = [slot for name in names for slot in slots(name)]
    existing = [slot for slot in desired if (claims / (slot + ".json")).exists()]
    if existing:
        raise RuntimeError("existing slot claims: " + ",".join(existing))
    for slot in desired:
        with (claims / (slot + ".json")).open("x", encoding="utf-8") as handle:
            reserved.append(slot)
            json.dump({"slot": slot, "owner": owner, "status": "reserved_no_retry"}, handle)


def verify(root: Path, *, names: tuple[str, ...] = NAMES) -> dict[str, Any]:
    """Verify staged source inputs, prior four-slot evidence, and child pins."""
    root = Path(root)
    manifest = json.loads((root / "batch_launch.json").read_text(encoding="utf-8"))
    staged = manifest.get("staged_files")
    if not isinstance(staged, dict):
        raise ValueError("staged file manifest required")
    required = {"icra_reference_batch.py", "prior_reference_report.json"} | {
        name + "/" + file for name in names for file in FILES
    }
    if not required <= set(staged):
        raise ValueError("incomplete staged coverage")
    for relative, expected in staged.items():
        path = root / relative
        resolved = path.resolve()
        if root.resolve() not in (resolved, *resolved.parents):
            raise ValueError("staged path outside batch")
        if sha(path) != expected:
            raise ValueError("staged hash mismatch: " + relative)
    total = (
        sum((root / relative).stat().st_size for relative in staged)
        + (root / "batch_launch.json").stat().st_size
    )
    if total > 1_000_000:
        raise ValueError("staged code/accounting input ceiling")
    prior = json.loads((root / "prior_reference_report.json").read_text(encoding="utf-8"))
    ids = ["H_attempt", "H_replay", "D_attempt", "D_replay"]
    rows = prior.get("rows", [])
    if (
        len(rows) != 4
        or [row["id"] for row in rows] != ids
        or prior.get("status") != "completed_attempt_accounting"
    ):
        raise ValueError("prior four-slot completion not reconciled")
    for row in rows:
        if row.get("error") or row.get("termination") not in (
            "native_success",
            "fixed_duration_exhausted",
            "environment_done_without_success",
        ):
            raise ValueError("prior terminal evidence invalid")
        if row["id"].endswith("replay") and row.get("fresh_replay_exact") is not True:
            raise ValueError("prior replay unverified")
    source = prior.get("source_pin", {})
    if source.get("task") != 0 or source.get("demo") != 0:
        raise ValueError("prior parent identity mismatch")
    for name in names:
        directory = root / name
        if (directory / "results").exists():
            raise ValueError("child results already exist: " + name)
        parents = json.loads((directory / "parents.json").read_text(encoding="utf-8"))
        if len(parents) != 1:
            raise ValueError("one source per child required")
        parent = parents[0]
        task, demo = parent["task"], parent["demo"]
        if type(task) is not int or type(demo) is not int or name != f"task-{task}-demo-{demo}":
            raise ValueError("folder/parent mismatch")
        child = json.loads((directory / "child.json").read_text(encoding="utf-8"))
        worlds = ["I"] if name == NAMES[0] else ["H", "D", "I"]
        if (
            type(child.get("task")) is not int
            or type(child.get("demo")) is not int
            or child.get("task") != task
            or child.get("demo") != demo
            or child.get("worlds") != worlds
            or type(child.get("retry")) is not int
            or child["retry"] != 0
        ):
            raise ValueError("child scope mismatch")
        gate = json.loads((directory / "physical_I_gate.json").read_text(encoding="utf-8"))
        if (
            gate.get("source_manifest_sha256") != parent["sha256"]
            or gate.get("physical_valid") is not True
            or gate.get("independent_review_complete") is not True
        ):
            raise ValueError("I gate mismatch")
        if sha(Path(gate["evidence_path"])) != gate["evidence_sha256"]:
            raise ValueError("I evidence changed")
        pins = json.loads((directory / "launch_pins.json").read_text(encoding="utf-8"))
        for file in FILES:
            if file != "launch_pins.json" and pins.get(file) != sha(directory / file):
                raise ValueError("child pin mismatch: " + name + "/" + file)
    return {
        "report_sha256": sha(root / "prior_reference_report.json"),
        "slots": rows,
        "source": source,
    }


def dispatch(
    root: Path,
    report: dict[str, Any],
    save: Callable[[], None],
    started: float,
    *,
    execute: Callable[[str], int],
    clock: Callable[[], float] = time.monotonic,
    names: tuple[str, ...] = NAMES,
) -> None:
    """Dispatch sequentially, preserving terminal child accounting and no retries."""
    for name in names:
        if clock() - started + 635 > 3900:
            raise TimeoutError("batch wall-time reserve")
        child: dict[str, Any] = {"id": name, "status": "started", "slots": slots(name)}
        report["children"].append(child)
        save()
        try:
            code = execute(name)
        except Exception as exc:
            child.update(status="terminal_observation_error", error=repr(exc))
            save()
            raise
        child.update(status="terminal", returncode=code)
        save()
        if code:
            raise RuntimeError("child failed; no subsequent children started")
        path = Path(root) / name / "results" / "report.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        child["report_sha256"] = sha(path)
        child["result_status"] = result.get("status")
        save()
        if result.get("status") != "completed_attempt_accounting":
            raise RuntimeError("child exit/result mismatch")
