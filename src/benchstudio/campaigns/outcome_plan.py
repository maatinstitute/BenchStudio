"""RoboPAD source-backed CPU-only outcome-campaign planning."""

from __future__ import annotations

import hashlib
import json
import re
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
