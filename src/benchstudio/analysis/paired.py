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
    success_gap_confidence_interval: tuple[float, float] | None = None


def clopper_pearson_interval(
    successes: int, trials: int, *, alpha: float = 0.05
) -> tuple[float, float]:
    """Return an exact two-sided binomial interval without SciPy."""
    if type(successes) is not int or type(trials) is not int:
        raise ValueError("successes and trials must be integers")
    if trials <= 0 or successes < 0 or successes > trials:
        raise ValueError("expected 0 <= successes <= trials with positive trials")
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie in (0, 1)")
    tail = alpha / 2
    lower = 0.0 if successes == 0 else _binomial_tail_quantile(successes - 1, trials, tail)
    upper = 1.0 if successes == trials else _binomial_cdf_quantile(successes, trials, tail)
    return lower, upper


def discordance_interval(
    wins: int, losses: int, trials: int, *, alpha: float = 0.05
) -> tuple[float, float]:
    """Bound paired success difference from discordant outcomes."""
    if type(wins) is not int or type(losses) is not int or type(trials) is not int:
        raise ValueError("discordance counts must be integers")
    if wins < 0 or losses < 0 or trials <= 0 or wins + losses > trials:
        raise ValueError("invalid discordance counts")
    low_w, high_w = clopper_pearson_interval(wins, trials, alpha=alpha)
    low_l, high_l = clopper_pearson_interval(losses, trials, alpha=alpha)
    return low_w - high_l, high_w - low_l


def _binomial_cdf(k: int, trials: int, probability: float) -> float:
    if k < 0:
        return 0.0
    if k >= trials:
        return 1.0
    return math.fsum(
        math.comb(trials, index) * probability**index * (1 - probability) ** (trials - index)
        for index in range(k + 1)
    )


def _binomial_tail_quantile(k: int, trials: int, tail: float) -> float:
    left, right = 0.0, 1.0
    for _ in range(100):
        middle = (left + right) / 2
        if 1.0 - _binomial_cdf(k, trials, middle) > tail:
            right = middle
        else:
            left = middle
    return (left + right) / 2


def _binomial_cdf_quantile(k: int, trials: int, tail: float) -> float:
    left, right = 0.0, 1.0
    for _ in range(100):
        middle = (left + right) / 2
        if _binomial_cdf(k, trials, middle) > tail:
            left = middle
        else:
            right = middle
    return (left + right) / 2


def summarize_paired_outcomes(
    outcomes_a: list[bool | None],
    outcomes_b: list[bool | None],
    numeric_a: list[float | None] | None = None,
    numeric_b: list[float | None] | None = None,
    *,
    alpha: float = 0.05,
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
    interval = discordance_interval(wins_b, wins_a, len(pairs), alpha=alpha) if pairs else None
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
        interval,
    )
