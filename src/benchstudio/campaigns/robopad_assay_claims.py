"""RoboPAD exclusive assay reservations, separate from execution and claim scoring."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GLOBAL_ROOT = Path("/cephhome/eunikhilr/alba/icra-protocol-development-20260914/assay-slot-claims")
HASH_KEYS = (
    "allocation_sha256",
    "replay_sha256",
    "child_manifest_sha256",
    "code_manifest_sha256",
    "source_sha256",
)
MAX_BYTES = 100_000


def canonical_runs(task: int, demo: int) -> list[str]:
    if (
        type(task) is not int
        or type(demo) is not int
        or task not in (0, 1, 2)
        or demo not in (0, 1)
    ):
        raise ValueError("invalid family")
    parent = f"task-{task}-demo-{demo}"
    rows = [
        f"{parent}-{controller}-{cell}-k{k}"
        for controller in ("vla", "reference", "insensitive")
        for cell in ("HH", "HD", "DH", "DD", "II")
        for k in (1, 5, 10, 20)
    ]
    if (task, demo) == (0, 0):
        used = {f"{parent}-vla-HH-k{k}" for k in (1, 5, 10, 20)} | {
            f"{parent}-vla-{cell}-k5" for cell in ("HD", "DH", "DD")
        }
        rows = [row for row in rows if row not in used]
    else:
        rows.append(parent + "-vla-HH-k5-replay")
    rows.append(parent + "-reference-DD-k20-replay")
    return rows


def _path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != str(value):
        raise ValueError("canonical absolute path required")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("symlinks forbidden")
    return path


def _inputs(root: str | Path, receipt: str | Path, bindings: dict[str, Any], runs: list[str]):
    root_path, receipt_path = _path(root), _path(receipt)
    if root_path != GLOBAL_ROOT or not root_path.is_dir():
        raise ValueError("fixed existing global claims root required")
    if not receipt_path.parent.is_dir():
        raise ValueError("receipt parent must exist")
    if set(bindings) != set(HASH_KEYS) | {"output_path"}:
        raise ValueError("binding schema mismatch")
    for key in HASH_KEYS:
        if (
            not isinstance(bindings[key], str)
            or re.fullmatch(r"[0-9a-f]{64}", bindings[key]) is None
        ):
            raise ValueError("invalid binding hash")
    _path(bindings["output_path"])
    if not isinstance(runs, list) or not runs or not all(isinstance(run, str) for run in runs):
        raise ValueError("explicit ordered run list required")
    match = re.fullmatch(
        r"task-([0-2])-demo-([01])-(?:vla|reference|insensitive)-(?:HH|HD|DH|DD|II)-k(?:1|5|10|20)(?:-replay)?",
        runs[0],
    )
    if match is None:
        raise ValueError("noncanonical slot")
    task, demo = map(int, match.groups())
    expected = canonical_runs(task, demo)
    if runs != expected:
        raise ValueError("exact remaining child allocation required")
    return root_path, receipt_path, f"task-{task}-demo-{demo}"


def _bytes(value: Any) -> bytes:
    raw = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("record byte ceiling")
    return raw


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _exclusive(path: str | Path, body: Any) -> str:
    path = _path(path)
    raw = _bytes(body)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        if stream.write(raw) != len(raw):
            raise OSError("short reservation write")
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(raw)


def _read(path: str | Path) -> tuple[Any, str]:
    path = _path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("regular record required")
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("record byte ceiling")
    value = json.loads(raw)
    if _bytes(value) != raw:
        raise ValueError("noncanonical or duplicate-key record")
    return value, _digest(raw)


def _claim(bindings: dict[str, Any], slot: str) -> dict[str, Any]:
    return {"schema": 1, "kind": "reserved_not_executed", "slot": slot, "bindings": bindings}


def reserve_child(
    claims_root: str | Path,
    receipt_path: str | Path,
    *,
    expected_bindings: dict[str, Any],
    expected_runs: list[str],
) -> dict[str, Any]:
    root, receipt, parent = _inputs(claims_root, receipt_path, expected_bindings, expected_runs)
    paths = [root / (run + ".json") for run in expected_runs]
    if receipt.exists() or any(path.exists() or path.is_symlink() for path in paths):
        raise FileExistsError("existing receipt/claim; no retries")
    hashes = {
        slot: _exclusive(path, _claim(expected_bindings, slot))
        for slot, path in zip(expected_runs, paths)
    }
    for slot, path in zip(expected_runs, paths):
        value, actual = _read(path)
        if value != _claim(expected_bindings, slot) or actual != hashes[slot]:
            raise ValueError("claim changed during reservation")
    value = {
        "schema": 1,
        "kind": "complete_reservation_not_execution",
        "parent": parent,
        "bindings": expected_bindings,
        "runs": expected_runs,
        "claims": hashes,
    }
    _exclusive(receipt, value)
    return value


def _verify(root: str | Path, receipt: str | Path, bindings: dict[str, Any], runs: list[str]):
    root, receipt, parent = _inputs(root, receipt, bindings, runs)
    value, receipt_digest = _read(receipt)
    if (
        set(value) != {"schema", "kind", "parent", "bindings", "runs", "claims"}
        or value["schema"] != 1
        or value["kind"] != "complete_reservation_not_execution"
        or value["parent"] != parent
        or value["bindings"] != bindings
        or value["runs"] != runs
        or set(value["claims"]) != set(runs)
    ):
        raise ValueError("reservation receipt mismatch")
    for slot in runs:
        claim, actual = _read(root / (slot + ".json"))
        if claim != _claim(bindings, slot) or actual != value["claims"][slot]:
            raise ValueError("claim mismatch")
    return value, receipt_digest, parent


@dataclass(frozen=True)
class StartedReservation:
    root: str
    receipt: str
    receipt_sha256: str
    proof: bytes
    started_path: str
    started_sha256: str


def verify_and_start(
    claims_root: str | Path,
    receipt_path: str | Path,
    *,
    expected_bindings: dict[str, Any],
    expected_runs: list[str],
) -> StartedReservation:
    value, receipt_digest, parent = _verify(
        claims_root, receipt_path, expected_bindings, expected_runs
    )
    started_path = Path(claims_root) / (parent + ".started")
    started_hash = _exclusive(
        started_path,
        {
            "schema": 1,
            "kind": "started_no_resume",
            "receipt_sha256": receipt_digest,
            "claims": value["claims"],
            "bindings": expected_bindings,
        },
    )
    return StartedReservation(
        str(claims_root),
        str(receipt_path),
        receipt_digest,
        _bytes(value),
        str(started_path),
        started_hash,
    )


def validate_claim(token: StartedReservation, run: str) -> str:
    if not isinstance(token, StartedReservation):
        raise ValueError("verified started reservation required")
    proof = json.loads(token.proof)
    if run not in proof["runs"]:
        raise ValueError("run outside reservation")
    value, receipt_digest, parent = _verify(
        token.root, token.receipt, proof["bindings"], proof["runs"]
    )
    if receipt_digest != token.receipt_sha256 or _bytes(value) != token.proof:
        raise ValueError("reservation changed after start")
    if token.started_path != str(Path(token.root) / (parent + ".started")):
        raise ValueError("wrong start path")
    marker, marker_hash = _read(token.started_path)
    expected = {
        "schema": 1,
        "kind": "started_no_resume",
        "receipt_sha256": receipt_digest,
        "claims": value["claims"],
        "bindings": proof["bindings"],
    }
    if marker != expected or marker_hash != token.started_sha256:
        raise ValueError("start proof changed")
    return value["claims"][run]
