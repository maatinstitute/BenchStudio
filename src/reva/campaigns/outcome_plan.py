"""RoboPAD source-backed CPU-only outcome-campaign planning."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

SCIENCE_SEEDS = (123, 456, 789, 1011, 1213)
TRAINING_ARMS = ("S", "M", "U", "C")
EVALUATION_BRANCHES = ("nominal", "displaced", "lighting")
RECOVERY_PARENT_COUNT = 24
RESET_PARENT_COUNT = 24
RECOVERY_PREFIX_STEPS = 5
RECOVERY_SUFFIX_HORIZON = 275
RESET_HORIZON = 300


def _validate_population(name: str, values: Iterable[str], expected_count: int) -> list[str]:
    population = list(values)
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", value)
        for value in population
    ):
        raise ValueError(f"{name} parent IDs must be path-safe")
    if len(set(population)) != len(population):
        raise ValueError(f"{name} parent IDs must be unique")
    if len(population) != expected_count:
        raise ValueError(f"{name} population must contain exactly {expected_count} parents")
    return population


def _training_cells() -> list[dict[str, object]]:
    return [
        {
            "cell_id": f"{arm}_seed{seed}",
            "arm": arm,
            "seed": seed,
            "kind": "training",
            "scientific_final_update": 64,
        }
        for arm in TRAINING_ARMS
        for seed in SCIENCE_SEEDS
    ]


def _evaluation_cells(
    kind: str, parents: list[str], policies: list[str]
) -> list[dict[str, object]]:
    branches = EVALUATION_BRANCHES if kind == "recovery" else ("nominal",)
    horizon = RECOVERY_SUFFIX_HORIZON if kind == "recovery" else RESET_HORIZON
    return [
        {
            "cell_id": f"{kind}__{parent}__{branch}__{policy}",
            "kind": kind,
            "parent_id": parent,
            "branch": branch,
            "policy_id": policy,
            "policy_queries_horizon": horizon,
        }
        for parent in parents
        for branch in branches
        for policy in policies
    ]


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_plan(
    *, recovery_parents: Iterable[str], reset_parents: Iterable[str]
) -> dict[str, object]:
    recovery = _validate_population("recovery", recovery_parents, RECOVERY_PARENT_COUNT)
    reset = _validate_population("reset", reset_parents, RESET_PARENT_COUNT)
    if set(recovery) & set(reset):
        raise ValueError("recovery and reset populations must be disjoint")
    training = _training_cells()
    policies = ["base"] + [row["cell_id"] for row in training]
    recovery_cells = _evaluation_cells("recovery", recovery, policies)
    reset_cells = _evaluation_cells("reset", reset, policies)
    payload: dict[str, object] = {
        "schema_version": "smolvla_outcome_plan_v1",
        "status": "preflight_only",
        "resource_authority_required": True,
        "training_cells": training,
        "recovery_cells": recovery_cells,
        "reset_cells": reset_cells,
        "constraints": {
            "training_arms": list(TRAINING_ARMS),
            "science_seeds": list(SCIENCE_SEEDS),
            "primary_contrast": "C_minus_U",
            "reserved_evaluation_requires_all_training_receipts": True,
            "recovery_prefix_steps": RECOVERY_PREFIX_STEPS,
            "recovery_suffix_horizon": RECOVERY_SUFFIX_HORIZON,
            "reset_horizon": RESET_HORIZON,
        },
        "counts": {
            "training_checkpoints": len(training),
            "recovery_continuations": len(recovery_cells),
            "reset_continuations": len(reset_cells),
            "reserved_continuations": len(recovery_cells) + len(reset_cells),
            "recovery_suffix_policy_queries": len(recovery_cells) * RECOVERY_SUFFIX_HORIZON,
            "recovery_shared_prefix_policy_queries": len(recovery) * RECOVERY_PREFIX_STEPS,
            "reset_policy_queries": len(reset_cells) * RESET_HORIZON,
            "max_policy_queries": (
                len(recovery_cells) * RECOVERY_SUFFIX_HORIZON
                + len(recovery) * RECOVERY_PREFIX_STEPS
                + len(reset_cells) * RESET_HORIZON
            ),
        },
    }
    payload["plan_sha256"] = _hash_payload(payload)
    return payload


def load_outcome_plan(path: Path) -> tuple[dict[str, object], str]:
    """Load a RoboPAD outcome plan and verify its self-contained contract.

    The plan is a preflight artifact, not an execution request.  ReVa
    records the source-file digest while preserving the source plan's own
    canonical payload digest and cell identities.
    """
    raw = path.read_bytes()
    file_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("RoboPAD outcome plan must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("RoboPAD outcome plan must be a mapping")
    verify_outcome_plan(payload)
    return payload, file_sha256


def verify_outcome_plan(payload: dict[str, object]) -> None:
    """Fail closed on a malformed or internally inconsistent outcome plan."""
    if payload.get("schema_version") != "smolvla_outcome_plan_v1":
        raise ValueError("unsupported RoboPAD outcome plan schema")
    if payload.get("status") != "preflight_only":
        raise ValueError("RoboPAD outcome plan must remain preflight_only")
    if payload.get("resource_authority_required") is not True:
        raise ValueError("RoboPAD outcome plan must require resource authority")
    declared_digest = payload.get("plan_sha256")
    if not isinstance(declared_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", declared_digest):
        raise ValueError("RoboPAD outcome plan digest is invalid")
    unsigned = {key: value for key, value in payload.items() if key != "plan_sha256"}
    if _hash_payload(unsigned) != declared_digest:
        raise ValueError("RoboPAD outcome plan digest mismatch")
    training = payload.get("training_cells")
    recovery = payload.get("recovery_cells")
    reset = payload.get("reset_cells")
    counts = payload.get("counts")
    constraints = payload.get("constraints")
    if not all(isinstance(value, list) for value in (training, recovery, reset)):
        raise ValueError("RoboPAD outcome plan cell collections must be lists")
    if not isinstance(counts, dict) or not isinstance(constraints, dict):
        raise ValueError("RoboPAD outcome plan counts and constraints are required")
    _validate_cells("training", training, expected_kind="training")
    _validate_cells("recovery", recovery, expected_kind="recovery")
    _validate_cells("reset", reset, expected_kind="reset")
    expected_counts = {
        "training_checkpoints": len(training),
        "recovery_continuations": len(recovery),
        "reset_continuations": len(reset),
        "reserved_continuations": len(recovery) + len(reset),
        "recovery_suffix_policy_queries": sum(
            int(row["policy_queries_horizon"]) for row in recovery
        ),
        "reset_policy_queries": sum(int(row["policy_queries_horizon"]) for row in reset),
    }
    shared_prefix_steps = constraints.get("recovery_prefix_steps")
    if type(shared_prefix_steps) is not int or shared_prefix_steps < 0:
        raise ValueError("RoboPAD recovery_prefix_steps is invalid")
    expected_counts["recovery_shared_prefix_policy_queries"] = (
        len({row["parent_id"] for row in recovery}) * shared_prefix_steps
    )
    expected_counts["max_policy_queries"] = (
        expected_counts["recovery_suffix_policy_queries"]
        + expected_counts["recovery_shared_prefix_policy_queries"]
        + expected_counts["reset_policy_queries"]
    )
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            raise ValueError(f"RoboPAD outcome plan count mismatch: {key}")


def _validate_cells(name: str, cells: list[object], *, expected_kind: str) -> None:
    required = (
        {"cell_id", "kind", "arm", "seed", "scientific_final_update"}
        if expected_kind == "training"
        else {"cell_id", "kind", "parent_id", "branch", "policy_id", "policy_queries_horizon"}
    )
    seen: set[str] = set()
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict) or not required.issubset(cell):
            raise ValueError(f"RoboPAD {name} cell {index} is incomplete")
        if cell["kind"] != expected_kind:
            raise ValueError(f"RoboPAD {name} cell {index} has the wrong kind")
        cell_id = cell["cell_id"]
        if not isinstance(cell_id, str) or not cell_id or cell_id in seen:
            raise ValueError(f"RoboPAD {name} cell IDs must be unique and non-empty")
        seen.add(cell_id)
        if expected_kind == "training":
            if not isinstance(cell["arm"], str) or type(cell["seed"]) is not int:
                raise ValueError(f"RoboPAD {name} cell {index} has invalid training identity")
            continue
        horizon = cell["policy_queries_horizon"]
        if type(horizon) is not int or horizon < 1:
            raise ValueError(f"RoboPAD {name} cell {index} has an invalid horizon")
