"""Source-backed Refinement/Refresh evaluation planning.

This module is a deliberate port of
``experiments/make_evaluation_plan.py`` from the Refinement/Refresh project.
Keep the canonicalization, keyed ordering, schema, and write semantics aligned
with that source; BenchStudio owns the adapter that turns a plan into frozen
campaign attempts.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

from .frozen_plan import AttemptKey, FrozenCampaignPlan, PlannedAttempt, _plan_digest

SCHEMA_VERSION = "1.0"
DEFAULT_SCHEDULING_SEED = 20260910
CHECKPOINT = "HuggingFaceVLA/smolvla_libero"
CHECKPOINT_REVISION = "6721902bc4d61e50a3bfdb11dfb4cb626f05d102"
SUITES = ("libero_spatial", "libero_object", "libero_goal", "libero_10")
TASK_IDS = (5, 6)
STATE_IDS = (10, 11, 12, 13, 14)
POLICY_SEEDS = (2000, 2001)
CONDITIONS = ((1, 5), (1, 10), (5, 5), (5, 10))
NATIVE_CONDITION = (1, 10)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def block_id(identity: tuple[str, int, int, int]) -> str:
    suite, task_id, state_id, policy_seed = identity
    return f"{suite}.task{task_id:03d}.state{state_id:03d}.seed{policy_seed}"


def make_plan(scheduling_seed: int = DEFAULT_SCHEDULING_SEED) -> dict[str, Any]:
    if not isinstance(scheduling_seed, int) or isinstance(scheduling_seed, bool):
        raise ValueError("scheduling seed must be an integer")
    identities = list(itertools.product(SUITES, TASK_IDS, STATE_IDS, POLICY_SEEDS))
    identities.sort(
        key=lambda identity: (digest([scheduling_seed, "block_order", identity]), identity)
    )
    schedule: list[dict[str, Any]] = []
    for block_index, identity in enumerate(identities):
        conditions = sorted(
            CONDITIONS,
            key=lambda condition: (
                digest([scheduling_seed, "condition_order", identity, condition]),
                condition,
            ),
        )
        episode_id = block_id(identity)
        for condition_index, (h, denoising_steps) in enumerate(conditions):
            condition_id = f"h{h}_d{denoising_steps}"
            schedule.append(
                {
                    "schedule_index": len(schedule),
                    "block_index": block_index,
                    "condition_index": condition_index,
                    "block_id": episode_id,
                    "episode_identity": {
                        "suite": identity[0],
                        "task_id": identity[1],
                        "initial_state_id": identity[2],
                        "policy_seed": identity[3],
                    },
                    "condition_id": condition_id,
                    "planned_run_id": f"{episode_id}.{condition_id}",
                    "h": h,
                    "denoising_steps": denoising_steps,
                    "native_reference": (h, denoising_steps) == NATIVE_CONDITION,
                }
            )
    return {
        "schema": "robopad.proposed_evaluation_plan",
        "schema_version": SCHEMA_VERSION,
        "design_revision": "2026-09-10",
        "status": "requires_runtime_and_holdout_verification",
        "purpose": "Proposed schedule only; no runs launched and no outcomes recorded.",
        "checkpoint": {
            "repository": CHECKPOINT,
            "revision": CHECKPOINT_REVISION,
            "runtime_file_hashes": None,
        },
        "native_config": {
            "predicted_chunk_size": 50,
            "n_action_steps": 1,
            "num_steps": 10,
            "condition_id": "h1_d10",
            "verification_status": "must_verify_against_loaded_config",
        },
        "design": {
            "suites": list(SUITES),
            "task_ids": list(TASK_IDS),
            "initial_state_ids": list(STATE_IDS),
            "policy_seeds": list(POLICY_SEEDS),
            "conditions": [{"h": h, "denoising_steps": d} for h, d in CONDITIONS],
            "task_count": len(SUITES) * len(TASK_IDS),
            "block_count": len(identities),
            "conditions_per_block": len(CONDITIONS),
            "planned_attempt_count": len(schedule),
            "estimand": "Exactly the eight declared tasks, equally weighted.",
        },
        "scheduling": {
            "seed": scheduling_seed,
            "algorithm": "sha256-keyed-sort-v1",
            "block_order_key": "SHA256(canonical_json([seed, 'block_order', identity_tuple]))",
            "condition_order_key": (
                "SHA256(canonical_json([seed, 'condition_order', identity_tuple, [h,d]]))"
            ),
            "identity_tuple_order": ["suite", "task_id", "initial_state_id", "policy_seed"],
            "canonicalization": "JSON sorted keys, compact separators, ensure_ascii=true, UTF-8",
            "digest_algorithm": "sha256",
            "digest_scope": "canonical JSON of the schedule array only",
            "schedule_sha256": digest(schedule),
        },
        "external_gates": {
            "runtime_and_loaded_config": "unverified",
            "initial_state_availability": "unverified",
            "held_out_against_all_archived_and_unarchived_runs": "unverified",
            "upstream_parity_and_instrumentation": "unverified",
            "hardware_allocation_and_measured_eta": "unverified",
        },
        "execution_contract": [
            "Keep all four conditions together within each episode block.",
            "Record actual reset-state hashes and independently keyed policy noise.",
            "Allocate a separate immutable attempt ID for every execution or retry.",
            "A planned_run_id is a design identity, not proof of an executed attempt.",
            "Refreeze the plan before new outcomes if any availability or overlap gate fails.",
            "Retain incomplete blocks and all attempts; never overwrite run evidence.",
        ],
        "schedule": schedule,
    }


def write_plan(path: Path, plan: dict[str, Any], *, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w" if force else "x", encoding="utf-8", newline="\n") as stream:
        json.dump(plan, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write("\n")


def compile_refinement_campaign_plan(
    *, run_id: str, scheduling_seed: int = DEFAULT_SCHEDULING_SEED
) -> FrozenCampaignPlan:
    """Adapt the source-backed schedule into BenchStudio's frozen plan type."""
    source_plan = make_plan(scheduling_seed)
    attempts: list[PlannedAttempt] = []
    for row in source_plan["schedule"]:
        identity = row["episode_identity"]
        attempts.append(
            PlannedAttempt(
                key=AttemptKey(
                    run_id=run_id,
                    scenario_id=f"{identity['suite']}:{identity['task_id']}",
                    pair_id=row["block_id"],
                    condition_id=row["condition_id"],
                    attempt_id=row["planned_run_id"],
                ),
                task_seed=identity["initial_state_id"],
                policy_seed=identity["policy_seed"],
                metadata={
                    "source_plan_schema": source_plan["schema"],
                    "source_schedule_sha256": source_plan["scheduling"]["schedule_sha256"],
                    "source_scheduling_seed": scheduling_seed,
                    "condition": {"h": row["h"], "denoising_steps": row["denoising_steps"]},
                    "episode_identity": dict(identity),
                    "native_reference": row["native_reference"],
                },
            )
        )
    digest_value = _plan_digest(
        run_id,
        attempts,
        paired_schedule=source_plan["schedule"],
        source_spec_sha256=source_plan["scheduling"]["schedule_sha256"],
        protocol={"source": "refinement-refresh-robot-policies", "schema": source_plan["schema"]},
    )
    return FrozenCampaignPlan(
        run_id=run_id,
        attempts=tuple(attempts),
        plan_digest_sha256=digest_value,
        paired_schedule=tuple(source_plan["schedule"]),
        source_spec_sha256=source_plan["scheduling"]["schedule_sha256"],
        protocol={"source": "refinement-refresh-robot-policies", "schema": source_plan["schema"]},
    )
