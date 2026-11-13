from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


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


def robopad_paired_bounds(plan: dict[Any, float], outcomes: dict[Any, Any]) -> dict[str, Any]:
    """Port RoboPAD's fixed-weight paired missing-outcome bounds.

    Unknown arms remain in the denominator and are bounded over every binary
    completion; observed data is never renormalized and no sampling interval
    is implied by this result.
    """
    if not plan or set(outcomes) - set(plan):
        raise ValueError("nonempty fixed plan required; unplanned outcomes forbidden")
    if any(
        not isinstance(weight, (int, float))
        or isinstance(weight, bool)
        or not math.isfinite(weight)
        or weight <= 0
        for weight in plan.values()
    ):
        raise ValueError("positive finite frozen weights required")
    if not math.isclose(math.fsum(plan.values()), 1.0, rel_tol=0, abs_tol=1e-12):
        raise ValueError("frozen weights must sum to one; no observed-data renormalization")
    lows: list[float] = []
    highs: list[float] = []
    missing = 0
    for identity, weight in plan.items():
        pair = outcomes.get(identity, (None, None))
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError("each record needs learner and original outcome")
        for value in pair:
            if value is not None and (
                isinstance(value, bool) is False
                and not isinstance(value, (int, float))
                or value not in (0, 1)
            ):
                raise ValueError("outcomes must be binary or explicitly unknown")
        learner, original = pair
        missing += sum(value is None for value in pair)
        learner_lo, learner_hi = (0, 1) if learner is None else (learner, learner)
        original_lo, original_hi = (0, 1) if original is None else (original, original)
        lows.append(weight * (learner_lo - original_hi))
        highs.append(weight * (learner_hi - original_lo))
    lower, upper = math.fsum(lows), math.fsum(highs)
    return {
        "lower": lower,
        "upper": upper,
        "point_estimate": lower if missing == 0 else None,
        "missing_arm_count": missing,
        "planned_pairs": len(plan),
        "sampling_uncertainty_included": False,
    }
