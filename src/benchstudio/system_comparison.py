"""Matched comparisons of two *whole systems* over archived experiments.

Uses BenchStudio's existing paired estimator. This module never re-runs a
system or treats incomplete, unqualified outcomes as failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, stdev

from .analysis.paired import PairedOutcomeSummary, summarize_paired_outcomes
from .system_evidence import SystemRun, Trial, TrialKey


@dataclass(frozen=True)
class MetricDelta:
    name: str
    matched: int
    mean_b_minus_a: float | None
    standard_error: float | None


@dataclass(frozen=True)
class SystemComparison:
    run_a: str
    run_b: str
    system_a_digest: str
    system_b_digest: str
    planned_union: int
    matched_conditions: int
    unmatched_a: tuple[TrialKey, ...]
    unmatched_b: tuple[TrialKey, ...]
    valid_binary_pairs: int
    incomplete_pairs: int
    paired_success: PairedOutcomeSummary
    numeric_deltas: tuple[MetricDelta, ...]
    interpretation: str = "DESCRIPTIVE_MATCHED_COMPARISON_NOT_CAUSAL_PROOF"


def compare_system_runs(
    a: SystemRun,
    b: SystemRun,
    *,
    metrics: tuple[str, ...] = (),
    alpha: float = 0.05,
) -> SystemComparison:
    """Compare declared paired units; retain missing/incomplete outcomes.

    TrialKey binds evaluator, environment revision, protocol, seeds and
    conditions, but does not independently prove physical reset parity.
    Numeric deltas are descriptive and have NO implicit reward direction.
    """
    if any(not isinstance(m, str) or not m.strip() for m in metrics):
        raise ValueError("metrics must be nonempty names")
    if len(set(metrics)) != len(metrics):
        raise ValueError("duplicate requested metric")
    records_a = {t.key: t for t in a.trials}
    records_b = {t.key: t for t in b.trials}
    shared = sorted(set(records_a) & set(records_b), key=repr)
    missing_a = tuple(sorted(set(records_b) - set(records_a), key=repr))
    missing_b = tuple(sorted(set(records_a) - set(records_b), key=repr))
    outcomes_a: list[bool | None] = []
    outcomes_b: list[bool | None] = []
    incomplete = 0
    for key in shared:
        va, vb = records_a[key], records_b[key]
        good_a, good_b = va.valid_success, vb.valid_success
        outcomes_a.append(va.success if good_a else None)
        outcomes_b.append(vb.success if good_b else None)
        if not good_a or not good_b:
            incomplete += 1
    paired = summarize_paired_outcomes(outcomes_a, outcomes_b, alpha=alpha)
    values: list[MetricDelta] = []
    for metric in metrics:
        deltas: list[float] = []
        for key in shared:
            ta, tb = records_a[key], records_b[key]
            if (
                ta.status == tb.status == "completed"
                and ta.authoritative and tb.authoritative
                and metric in ta.metrics and metric in tb.metrics
            ):
                deltas.append(float(tb.metrics[metric]) - float(ta.metrics[metric]))
        values.append(MetricDelta(
            metric, len(deltas), mean(deltas) if deltas else None,
            stdev(deltas) / len(deltas) ** 0.5 if len(deltas) > 1 else None,
        ))
    return SystemComparison(
        run_a=a.run_id, run_b=b.run_id,
        system_a_digest=a.system.digest, system_b_digest=b.system.digest,
        planned_union=len(set(records_a) | set(records_b)),
        matched_conditions=len(shared), unmatched_a=missing_a,
        unmatched_b=missing_b, valid_binary_pairs=paired.matched_pairs,
        incomplete_pairs=incomplete, paired_success=paired,
        numeric_deltas=tuple(values),
    )
