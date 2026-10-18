from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MissingOutcomeBounds:
    scheduled: int
    observed: int
    successes: int
    lower_success_rate: float | None
    upper_success_rate: float | None
    missing: int


def missing_outcome_bounds(
    *, scheduled: int, observed: int, successes: int
) -> MissingOutcomeBounds:
    if scheduled < 0 or observed < 0 or successes < 0:
        raise ValueError("counts must be non-negative")
    if observed > scheduled or successes > observed:
        raise ValueError("counts violate scheduled/observed bounds")
    missing = scheduled - observed
    return MissingOutcomeBounds(
        scheduled=scheduled,
        observed=observed,
        successes=successes,
        lower_success_rate=successes / scheduled if scheduled else None,
        upper_success_rate=(successes + missing) / scheduled if scheduled else None,
        missing=missing,
    )
