from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DeadlineAudit:
    scheduled_calls: int
    completed_calls: int
    missed_deadlines: int
    max_latency_ms: float | None
    valid: bool
    issues: tuple[str, ...]


def audit_deadlines(
    latencies_ms: list[float], *, scheduled_calls: int, deadline_ms: float
) -> DeadlineAudit:
    issues: list[str] = []
    valid_scheduled = isinstance(scheduled_calls, int) and not isinstance(scheduled_calls, bool)
    valid_deadline = (
        isinstance(deadline_ms, (int, float))
        and not isinstance(deadline_ms, bool)
        and math.isfinite(float(deadline_ms))
        and deadline_ms >= 0
    )
    if not valid_scheduled:
        issues.append("scheduled_calls must be a non-negative integer")
    elif scheduled_calls < 0:
        issues.append("scheduled_calls must be non-negative")
    if not valid_deadline:
        issues.append("deadline_ms must be finite and non-negative")
    valid_latencies: list[float] = []
    invalid_indices: list[int] = []
    for index, value in enumerate(latencies_ms):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
        ):
            invalid_indices.append(index)
        else:
            valid_latencies.append(float(value))
    if invalid_indices:
        issues.append(
            "latencies must be finite and non-negative numbers at indices: "
            + ", ".join(str(index) for index in invalid_indices)
        )
    if valid_scheduled and len(latencies_ms) > scheduled_calls:
        issues.append("completed calls exceed scheduled calls")
    if valid_scheduled and len(latencies_ms) != scheduled_calls:
        issues.append("deadline audit is incomplete")
    missed = sum(value > deadline_ms for value in valid_latencies) if valid_deadline else 0
    return DeadlineAudit(
        scheduled_calls,
        len(latencies_ms),
        missed,
        max(valid_latencies) if valid_latencies else None,
        not issues,
        tuple(issues),
    )
