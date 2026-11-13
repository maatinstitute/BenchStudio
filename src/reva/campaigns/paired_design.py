from __future__ import annotations

from typing import Any, Iterable

from .frozen_plan import AttemptKey, FrozenCampaignPlan, PlannedAttempt, _plan_digest
from .refinement_plan import canonical_json, digest


def compile_balanced_paired_plan(
    *,
    run_id: str,
    scenario_id: str,
    suites: Iterable[str],
    task_ids: Iterable[int],
    initial_state_ids: Iterable[int],
    policy_seeds: Iterable[int],
    conditions: Iterable[dict[str, Any]],
    scenario_pack_digest: str | None = None,
) -> FrozenCampaignPlan:
    """Compile complete matched condition blocks from a frozen design grid.

    The ordering uses SHA-256 keyed sorting, mirroring the upstream research
    runner's deterministic schedule while producing REVA attempts.
    """
    conditions = tuple(dict(condition) for condition in conditions)
    identities = [
        (suite, task_id, state_id, policy_seed)
        for suite in suites
        for task_id in task_ids
        for state_id in initial_state_ids
        for policy_seed in policy_seeds
    ]
    if not identities or not conditions:
        raise ValueError("paired design identities and conditions must not be empty")
    if len({_canonical(condition) for condition in conditions}) != len(conditions):
        raise ValueError("paired design contains duplicate conditions")
    identities.sort(key=lambda identity: (_digest([run_id, "block_order", identity]), identity))
    attempts: list[PlannedAttempt] = []
    schedule: list[dict[str, Any]] = []
    for block_index, identity in enumerate(identities):
        suite, task_id, state_id, policy_seed = identity
        pair_id = _digest(
            {
                "scenario_id": scenario_id,
                "scenario_pack_digest": scenario_pack_digest,
                "suite": suite,
                "task_id": task_id,
                "initial_state_id": state_id,
                "policy_seed": policy_seed,
            }
        )[:16]
        ordered_conditions = sorted(
            conditions,
            key=lambda condition: (
                _digest([run_id, "condition_order", identity, condition]),
                _canonical(condition),
            ),
        )
        block_id = f"{suite}.task{task_id:03d}.state{state_id:03d}.seed{policy_seed}"
        for condition_index, condition in enumerate(ordered_conditions):
            attempt_id = f"attempt-{len(attempts):06d}"
            key = AttemptKey(
                run_id,
                f"{scenario_id}:{suite}:{task_id}",
                pair_id,
                _digest(condition)[:16],
                attempt_id,
            )
            metadata = {
                "condition": condition,
                "suite": suite,
                "task_id": task_id,
                "initial_state_id": state_id,
                "policy_seed": policy_seed,
                "block_id": block_id,
                "block_index": block_index,
                "condition_index": condition_index,
                "scenario_pack_digest": scenario_pack_digest,
            }
            attempts.append(
                PlannedAttempt(key, task_seed=state_id, policy_seed=policy_seed, metadata=metadata)
            )
            schedule.append(
                {
                    "attempt_id": attempt_id,
                    "pair_id": pair_id,
                    "block_id": block_id,
                    "condition_id": key.condition_id,
                    "episode_identity": {
                        "suite": suite,
                        "task_id": task_id,
                        "initial_state_id": state_id,
                        "policy_seed": policy_seed,
                    },
                }
            )
    digest = _plan_digest(
        run_id,
        attempts,
        paired_schedule=schedule,
        source_spec_sha256=None,
        protocol=None,
    )
    return FrozenCampaignPlan(run_id, tuple(attempts), digest, tuple(schedule))


def _canonical(value: Any) -> str:
    return canonical_json(value).decode("utf-8")


def _digest(value: Any) -> str:
    return digest(value)
