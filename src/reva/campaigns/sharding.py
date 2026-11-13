"""Deterministic scheduler sharding for frozen campaign plans."""

from __future__ import annotations

from .frozen_plan import FrozenCampaignPlan


def shard_attempt_ids(
    plan: FrozenCampaignPlan, *, shard_index: int, shard_count: int
) -> tuple[str, ...]:
    """Return one stable, disjoint round-robin slice of a frozen plan.

    Sharding never rewrites the plan or attempt identities.  Every scheduler
    task must load the same frozen plan, then select its assigned slice.
    """
    if (
        isinstance(shard_count, bool)
        or not isinstance(shard_count, int)
        or shard_count < 1
    ):
        raise ValueError("shard_count must be a positive integer")
    if (
        isinstance(shard_index, bool)
        or not isinstance(shard_index, int)
        or not 0 <= shard_index < shard_count
    ):
        raise ValueError("shard_index must satisfy 0 <= shard_index < shard_count")
    if shard_count > len(plan.attempts):
        raise ValueError("shard_count must not exceed the number of planned attempts")
    return tuple(
        attempt.key.attempt_id
        for position, attempt in enumerate(plan.attempts)
        if position % shard_count == shard_index
    )
