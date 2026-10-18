from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PairedOutcomeSummary:
    matched_pairs: int
    wins_a: int
    wins_b: int
    ties: int
    success_rate_a: float | None
    success_rate_b: float | None
    success_gap_b_minus_a: float | None
    mean_numeric_delta_b_minus_a: float | None
    standard_error_numeric_delta: float | None


def summarize_paired_outcomes(
    outcomes_a: list[bool | None],
    outcomes_b: list[bool | None],
    numeric_a: list[float | None] | None = None,
    numeric_b: list[float | None] | None = None,
) -> PairedOutcomeSummary:
    if len(outcomes_a) != len(outcomes_b):
        raise ValueError("paired outcome lists must have equal length")
    pairs = [(a, b) for a, b in zip(outcomes_a, outcomes_b) if a is not None and b is not None]
    wins_a = sum(a and not b for a, b in pairs)
    wins_b = sum(b and not a for a, b in pairs)
    ties = len(pairs) - wins_a - wins_b
    rate_a = sum(a for a, _ in pairs) / len(pairs) if pairs else None
    rate_b = sum(b for _, b in pairs) / len(pairs) if pairs else None
    deltas: list[float] = []
    if numeric_a is not None or numeric_b is not None:
        if (
            numeric_a is None
            or numeric_b is None
            or len(numeric_a) != len(numeric_b)
            or len(numeric_a) != len(outcomes_a)
        ):
            raise ValueError("numeric paired lists must match outcome list length")
        deltas = [
            float(b) - float(a)
            for a, b in zip(numeric_a, numeric_b)
            if a is not None and b is not None
        ]
    mean_delta = sum(deltas) / len(deltas) if deltas else None
    standard_error = None
    if len(deltas) > 1:
        variance = sum((delta - mean_delta) ** 2 for delta in deltas) / (len(deltas) - 1)
        standard_error = math.sqrt(variance / len(deltas))
    return PairedOutcomeSummary(
        len(pairs),
        wins_a,
        wins_b,
        ties,
        rate_a,
        rate_b,
        rate_b - rate_a if rate_a is not None and rate_b is not None else None,
        mean_delta,
        standard_error,
    )
