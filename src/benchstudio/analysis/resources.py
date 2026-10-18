from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceBudget:
    max_inference_calls: int | None = None
    max_wall_time_ms: float | None = None
    max_compute_time_ms: float | None = None


@dataclass(frozen=True)
class ResourceAudit:
    valid: bool
    violations: tuple[str, ...]


def audit_resources(
    *, calls: int, wall_time_ms: float, compute_time_ms: float, budget: ResourceBudget
) -> ResourceAudit:
    violations: list[str] = []
    if budget.max_inference_calls is not None and calls > budget.max_inference_calls:
        violations.append("inference_call_budget_exceeded")
    if budget.max_wall_time_ms is not None and wall_time_ms > budget.max_wall_time_ms:
        violations.append("wall_time_budget_exceeded")
    if budget.max_compute_time_ms is not None and compute_time_ms > budget.max_compute_time_ms:
        violations.append("compute_time_budget_exceeded")
    return ResourceAudit(not violations, tuple(violations))
