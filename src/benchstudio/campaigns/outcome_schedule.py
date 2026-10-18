"""Deterministic, hashable S/M/U/C exposure schedules."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

ARMS = ("S", "M", "U", "C")
WINDOW = 50


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _row(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("valid_positions") != WINDOW:
        raise ValueError("schedule rows must contain 50 valid positions")
    for key in ("sample_id", "task_id", "branch", "trajectory_id", "outcome", "action_start"):
        if key not in row:
            raise ValueError(f"schedule row missing {key}")
        if row[key] is None:
            raise ValueError(f"schedule row missing {key}")
    if row["outcome"] not in {"success", "failure"}:
        raise ValueError("schedule rows require known success/failure outcomes")
    if type(row["action_start"]) is not int or row["action_start"] < 0:
        raise ValueError("schedule row action_start must be a nonnegative integer")
    normalized = {
        key: row[key]
        for key in (
            "sample_id",
            "task_id",
            "branch",
            "parent_id",
            "trajectory_id",
            "outcome",
            "action_start",
            "valid_positions",
        )
    }
    for key in ("task", "observation_path", "observation_sha256", "action_path", "action_sha256"):
        if key in row:
            normalized[key] = row[key]
    return normalized


def _group(
    rows: Iterable[dict[str, Any]], *, required_strata: Iterable[tuple[Any, str]] = ()
) -> tuple[dict[tuple[Any, str], dict[str, list[dict[str, Any]]]], list[tuple[Any, str]]]:
    groups: dict[tuple[Any, str], dict[str, list[dict[str, Any]]]] = {}
    for source in rows:
        row = _row(source)
        key = (row["task_id"], row["branch"])
        groups.setdefault(key, {"success": [], "failure": []})[row["outcome"]].append(row)
    usable = {key: value for key, value in groups.items() if value["success"] and value["failure"]}
    excluded = sorted(
        (key for key, value in groups.items() if not value["success"] or not value["failure"]),
        key=lambda item: (str(item[0]), str(item[1])),
    )
    missing_required = [key for key in required_strata if key not in usable]
    if missing_required:
        raise ValueError(f"required stratum lacks both outcomes: {missing_required}")
    if not usable:
        raise ValueError("no two-class task/branch stratum available")
    for value in usable.values():
        for outcome in value:
            value[outcome].sort(key=lambda item: (item["sample_id"], item["action_start"]))
    return usable, excluded


def _hierarchical_pick(
    group: dict[str, list[dict[str, Any]]], *, seed: int, offset: int
) -> dict[str, Any]:
    """Pick uniformly by parent, then trajectory, then valid window start."""
    by_parent: dict[Any, dict[str, list[dict[str, Any]]]] = {}
    for row in group:
        by_parent.setdefault(row.get("parent_id"), {}).setdefault(row["trajectory_id"], []).append(
            row
        )
    parents = sorted(by_parent, key=lambda value: str(value))
    # Independent deterministic draws avoid the modular walk starving
    # parents when the number of windows shares factors with the parent count.
    parent = parents[random.Random(seed + 1000003 * offset).randrange(len(parents))]
    trajectories = sorted(by_parent[parent])
    trajectory = trajectories[
        random.Random(seed + 1000003 * offset + 9176).randrange(len(trajectories))
    ]
    windows = sorted(
        by_parent[parent][trajectory], key=lambda item: (item["sample_id"], item["action_start"])
    )
    return windows[random.Random(seed + 1000003 * offset + 18352).randrange(len(windows))]


def _hierarchical_picks(
    group: list[dict[str, Any]],
    *,
    seed: int,
    offset: int,
    count: int,
    excluded: set[Any] | None = None,
) -> list[dict[str, Any]]:
    """Draw deterministic independent samples under the stated hierarchy."""
    candidates = [row for row in group if not excluded or row["sample_id"] not in excluded]
    if not candidates:
        # Reuse is permitted by the handoff when a class has fewer than eight
        # eligible windows; never invent a minimum-population requirement.
        candidates = list(group)
    return [
        _hierarchical_pick(candidates, seed=seed, offset=offset + index) for index in range(count)
    ]


@dataclass
class ScheduleReceipt:
    config: dict[str, Any]
    rows_by_update: list[dict[str, Any]]
    exposure: dict[str, dict[str, int]]
    schedule_sha256: str


def _payload(receipt: ScheduleReceipt) -> dict[str, Any]:
    return {
        "config": receipt.config,
        "rows_by_update": receipt.rows_by_update,
        "exposure": receipt.exposure,
    }


def build_schedule(
    rows: Iterable[dict[str, Any]],
    *,
    seed: int,
    updates: int = 64,
    windows_per_update: int = 8,
    required_strata: Iterable[tuple[Any, str]] = (),
) -> ScheduleReceipt:
    if type(seed) is not int or updates <= 0 or windows_per_update != 8:
        raise ValueError(
            "schedule requires integer seed, positive updates, and eight windows per update"
        )
    groups, excluded_strata = _group(rows, required_strata=required_strata)
    strata = sorted(groups, key=lambda item: (str(item[0]), str(item[1])))
    updates_out: list[dict[str, Any]] = []
    masks = [[1] * WINDOW for _ in range(windows_per_update)]
    for update in range(updates):
        key = strata[(seed + update) % len(strata)]
        group = groups[key]
        base_offset = update * 8
        positives = _hierarchical_picks(group["success"], seed=seed, offset=base_offset, count=4)
        failures = _hierarchical_picks(
            group["failure"],
            seed=seed,
            offset=base_offset,
            count=4,
            excluded={row["sample_id"] for row in positives},
        )
        mixed = positives + failures
        s_positive = _hierarchical_picks(
            group["success"],
            seed=seed,
            offset=base_offset + 4,
            count=4,
            excluded={row["sample_id"] for row in positives},
        )
        success_only = positives + s_positive
        update_rows = {
            "S": success_only,
            "M": mixed,
            "U": list(mixed),
            "C": list(mixed),
            "S_masks": [list(mask) for mask in masks],
            "M_masks": [list(mask) for mask in masks],
            "U_masks": [list(mask) for mask in masks],
            "C_masks": [list(mask) for mask in masks],
        }
        updates_out.append(update_rows)
    exposure = {
        arm: {
            "windows": updates * windows_per_update,
            "valid_positions": updates * windows_per_update * WINDOW,
        }
        for arm in ARMS
    }
    receipt = ScheduleReceipt(
        config={
            "seed": seed,
            "updates": updates,
            "windows_per_update": windows_per_update,
            "valid_positions_per_window": WINDOW,
            "arm_order": list(ARMS),
            "excluded_strata": [[key, branch] for key, branch in excluded_strata],
        },
        rows_by_update=updates_out,
        exposure=exposure,
        schedule_sha256="",
    )
    validate_schedule(receipt, require_hash=False)
    receipt.schedule_sha256 = _digest(_payload(receipt))
    return receipt


def validate_schedule(receipt: ScheduleReceipt, *, require_hash: bool = True) -> None:
    if receipt.config.get("updates") != len(receipt.rows_by_update):
        raise ValueError("schedule config updates do not match rows")
    if receipt.config.get("windows_per_update") != 8:
        raise ValueError("schedule must use eight windows per update")
    for update in receipt.rows_by_update:
        for arm in ARMS:
            if arm not in update or len(update[arm]) != 8:
                raise ValueError("schedule is missing an arm or has the wrong exposure")
            masks = update.get(f"{arm}_masks")
            if not isinstance(masks, list) or len(masks) != 8:
                raise ValueError("schedule is missing an arm mask")
            for row in update[arm]:
                _row(row)
        if update["M"] != update["U"] or update["M"] != update["C"]:
            raise ValueError("M/U/C ordered rows must agree")
        if update["M_masks"] != update["U_masks"] or update["M_masks"] != update["C_masks"]:
            raise ValueError("M/U/C masks must agree")
        if any(
            len(mask) != WINDOW or any(value != 1 for value in mask)
            for arm in ARMS
            for mask in update[f"{arm}_masks"]
        ):
            raise ValueError("each schedule mask must contain 50 valid positions")
        if [row["sample_id"] for row in update["M"]].count(None):
            raise ValueError("schedule rows require sample IDs")
        if [row["outcome"] for row in update["M"]] != ["success"] * 4 + ["failure"] * 4:
            raise ValueError("M requires four success and four failure slots")
        if update["S"][:4] != update["M"][:4] or any(
            row["outcome"] != "success" for row in update["S"]
        ):
            raise ValueError("S must share positive slots and contain only successes")
        if any(
            (row["task_id"], row["branch"])
            != (update["M"][index]["task_id"], update["M"][index]["branch"])
            for index, row in enumerate(update["S"][4:], start=4)
        ):
            raise ValueError("S replacement has a foreign task/branch")
        for arm in ARMS:
            if any(row.get("valid_positions") != WINDOW for row in update[arm]):
                raise ValueError("schedule row has invalid mask exposure")
    expected = receipt.exposure
    updates = len(receipt.rows_by_update)
    for arm in ARMS:
        if expected.get(arm) != {"windows": updates * 8, "valid_positions": updates * 8 * WINDOW}:
            raise ValueError("exposure counters do not match rows")
    if require_hash:
        if not isinstance(receipt.schedule_sha256, str) or len(receipt.schedule_sha256) != 64:
            raise ValueError("schedule hash is required")
        if receipt.schedule_sha256 != _digest(_payload(receipt)):
            raise ValueError("schedule hash mismatch")


def write_schedule(receipt: ScheduleReceipt, path: str) -> str:
    validate_schedule(receipt)
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n")
    temporary.replace(target)
    return str(target)


def read_schedule(path: str) -> ScheduleReceipt:
    data = json.loads(Path(path).read_text())
    receipt = ScheduleReceipt(**data)
    validate_schedule(receipt)
    return receipt
