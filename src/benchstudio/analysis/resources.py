from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ResourceBudget:
    max_inference_calls: int | None = None
    max_wall_time_ms: float | None = None
    max_compute_time_ms: float | None = None


@dataclass(frozen=True)
class ResourceAudit:
    valid: bool
    violations: tuple[str, ...]


@dataclass(frozen=True)
class ResourcePoint:
    condition_id: str
    success_rate: float
    latency_ms: float
    compute_ms: float


def pareto_frontier(points: Iterable[ResourcePoint]) -> tuple[ResourcePoint, ...]:
    """Return non-dominated points: higher success, lower latency and compute."""
    ordered = sorted(points, key=lambda point: point.condition_id)
    for point in ordered:
        if point.success_rate < 0 or point.success_rate > 1:
            raise ValueError(f"success_rate out of range for {point.condition_id}")
        if point.latency_ms < 0 or point.compute_ms < 0:
            raise ValueError(f"resource values must be non-negative for {point.condition_id}")
    frontier: list[ResourcePoint] = []
    for candidate in ordered:
        dominated = any(
            other is not candidate
            and other.success_rate >= candidate.success_rate
            and other.latency_ms <= candidate.latency_ms
            and other.compute_ms <= candidate.compute_ms
            and (
                other.success_rate > candidate.success_rate
                or other.latency_ms < candidate.latency_ms
                or other.compute_ms < candidate.compute_ms
            )
            for other in ordered
        )
        if not dominated:
            frontier.append(candidate)
    return tuple(frontier)


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
