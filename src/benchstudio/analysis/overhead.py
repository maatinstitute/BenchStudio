from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionOverhead:
    matched_samples: int
    baseline_mean_ms: float | None
    instrumented_mean_ms: float | None
    added_mean_ms: float | None
    relative_overhead: float | None
    baseline_deadline_misses: int
    instrumented_deadline_misses: int
    valid: bool
    issues: tuple[str, ...]


def audit_execution_overhead(
    baseline_ms: list[float],
    instrumented_ms: list[float],
    *,
    deadline_ms: float | None = None,
) -> ExecutionOverhead:
    """Compare same-unit timing samples without hiding missing or invalid data."""
    issues: list[str] = []
    if len(baseline_ms) != len(instrumented_ms):
        return ExecutionOverhead(
            0,
            None,
            None,
            None,
            None,
            0,
            0,
            False,
            ("baseline and instrumented samples must have equal length",),
        )
    if deadline_ms is not None and (not math.isfinite(float(deadline_ms)) or deadline_ms < 0):
        issues.append("deadline_ms must be finite and non-negative")
    for label, values in (("baseline", baseline_ms), ("instrumented", instrumented_ms)):
        for index, value in enumerate(values):
            if not math.isfinite(float(value)) or value < 0:
                issues.append(f"{label}[{index}] must be finite and non-negative")
    if issues:
        return ExecutionOverhead(
            len(baseline_ms), None, None, None, None, 0, 0, False, tuple(issues)
        )
    if not baseline_ms:
        return ExecutionOverhead(0, None, None, None, None, 0, 0, False, ("no timing samples",))
    baseline_mean = sum(baseline_ms) / len(baseline_ms)
    instrumented_mean = sum(instrumented_ms) / len(instrumented_ms)
    added = instrumented_mean - baseline_mean
    relative = added / baseline_mean if baseline_mean > 0 else None
    baseline_misses = (
        sum(value > deadline_ms for value in baseline_ms) if deadline_ms is not None else 0
    )
    instrumented_misses = (
        sum(value > deadline_ms for value in instrumented_ms) if deadline_ms is not None else 0
    )
    return ExecutionOverhead(
        len(baseline_ms),
        baseline_mean,
        instrumented_mean,
        added,
        relative,
        baseline_misses,
        instrumented_misses,
        True,
        (),
    )
