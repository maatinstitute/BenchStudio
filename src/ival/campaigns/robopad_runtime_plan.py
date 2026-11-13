"""RoboPAD fixed child-run and allocation-manifest contracts."""

from __future__ import annotations

from typing import Any

from .robopad_assay_plan import CONSUMED, all_slots, remaining_slots, suffix_seed

ALLOCATION_SHA = "48fd05bbee3caf771cae05be2070ec13d4f43df9510902be1f83c0a6700c36a9"
INITIALIZATION_VERSION = "restored_pose_goals_v1"


def slot_name(slot: tuple[int, int, str, str, int]) -> str:
    task, demo, controller, cell, horizon = slot
    return f"task-{task}-demo-{demo}-{controller}-{cell}-k{horizon}"


def child_runs(task: int, demo: int) -> list[dict[str, Any]]:
    if (
        type(task) is not int
        or type(demo) is not int
        or task not in range(3)
        or demo not in range(2)
    ):
        raise ValueError("fixed exposed parent required")
    runs: list[dict[str, Any]] = []
    replays: list[dict[str, Any]] = []
    for slot in remaining_slots():
        if slot[:2] != (task, demo):
            continue
        runs.append({"id": slot_name(slot), "slot": list(slot), "kind": "assay"})
        if (slot[2], slot[3], slot[4]) in (("reference", "DD", 20), ("vla", "HH", 5)):
            replays.append(
                {
                    "id": slot_name(slot) + "-replay",
                    "slot": list(slot),
                    "kind": "replay",
                    "original": slot_name(slot),
                }
            )
    runs.extend(replays)
    return runs


def validate_plan(config: dict[str, Any]) -> list[dict[str, Any]]:
    if config.get("initialization_version") != INITIALIZATION_VERSION:
        raise ValueError("explicit restored initialization version required")
    runs = child_runs(config["task"], config["demo"])
    if config.get("runs") != runs:
        raise ValueError("child allocation/replay order mismatch")
    if (
        config.get("allocation_sha256") != ALLOCATION_SHA
        or config.get("allocation_manifest", {}).get("sha256") != ALLOCATION_SHA
    ):
        raise ValueError("full immutable allocation artifact hash required")
    if config.get("allocation") != [list(slot) for slot in remaining_slots()]:
        raise ValueError("full353 allocation mismatch")
    limits = config["limits"]
    for key in (
        "application_seconds",
        "total_bytes",
        "cache_bytes",
        "cell_bytes",
        "accounting_bytes",
        "max_actions",
        "max_suffix_queries",
        "max_cache_queries",
    ):
        if type(limits.get(key)) is not int or limits[key] <= 0:
            raise ValueError("explicit positive limits required: " + key)
    reserve = config.get("cell_runtime_reserve_seconds")
    if type(reserve) is not int or not 1 <= reserve <= limits["application_seconds"] - 15:
        raise ValueError("invalid cell runtime reserve")
    cache_count = 2 if (config["task"], config["demo"]) == (0, 0) else 6
    if (
        limits["max_cache_queries"] != cache_count
        or limits["max_actions"] != 200 * len(runs)
        or limits["max_suffix_queries"] != 20 * len(runs)
    ):
        raise ValueError("query/action ceilings differ from fixed plan")
    if (
        limits["cache_bytes"] + len(runs) * limits["cell_bytes"] + limits["accounting_bytes"]
        > limits["total_bytes"]
    ):
        raise ValueError("unreserved child storage")
    if (config["task"], config["demo"]) == (0, 0) and (
        limits["application_seconds"] > 3300 or limits["total_bytes"] > 4_000_000_000
    ):
        raise ValueError("first-child draft ceiling exceeded")
    if (
        limits["cell_bytes"] < 60_000
        or limits["cache_bytes"] < 20_000
        or limits["accounting_bytes"] < 10_000
    ):
        raise ValueError("insufficient fixed failure reserves")
    return runs


def validate_allocation_manifest(artifact: dict[str, Any]) -> list[tuple[int, int, str, str, int]]:
    if (
        artifact.get("version") != 1
        or artifact.get("status") != "identity_allocation_only_not_launch_authorization"
    ):
        raise ValueError("allocation artifact schema")
    rows = artifact.get("rows", [])
    if len(rows) != 360:
        raise ValueError("full360 allocation required")
    identities = []
    unused = []
    for row in rows:
        task, demo, horizon = row["task"], row["demo"], row["horizon"]
        if any(type(value) is not int for value in (task, demo, horizon)):
            raise ValueError("allocation integer identity")
        slot = (task, demo, row["controller"], row["world"] + row["source"], horizon)
        if row["id"] != slot_name(slot) or row["total_action_cap"] != 200:
            raise ValueError("allocation row identity/cap")
        status = "already_consumed" if slot in CONSUMED else "unconsumed"
        if row["status"] != status:
            raise ValueError("historical consumed status changed")
        if row["suffix_seed_base"] != suffix_seed(task, demo, 0) or row[
            "suffix_query_steps"
        ] != list(range(horizon, 200, 10)):
            raise ValueError("allocation noise/query schedule changed")
        identities.append(slot)
        if status == "unconsumed":
            unused.append(slot)
    if identities != list(all_slots()) or unused != list(remaining_slots()):
        raise ValueError("allocation ordering/coverage mismatch")
    return unused
