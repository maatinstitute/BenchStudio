from __future__ import annotations

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
    if scheduled_calls < 0 or deadline_ms < 0:
        issues.append("scheduled_calls and deadline_ms must be non-negative")
    if len(latencies_ms) > scheduled_calls:
        issues.append("completed calls exceed scheduled calls")
    if any(value < 0 for value in latencies_ms):
        issues.append("latencies must be non-negative")
    missed = sum(value > deadline_ms for value in latencies_ms if value >= 0)
    if len(latencies_ms) != scheduled_calls:
        issues.append("deadline audit is incomplete")
    return DeadlineAudit(
        scheduled_calls,
        len(latencies_ms),
        missed,
        max(latencies_ms) if latencies_ms else None,
        not issues,
        tuple(issues),
    )
