from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ResourceBudget:
    max_inference_calls: int | None = None
    max_wall_time_ms: float | None = None
    max_compute_time_ms: float | None = None
    # Campaign-level ceilings carried from RoboPAD's frozen outcome manifest.
    # They remain optional so existing local runs keep their smaller contract.
    max_gpu_hours: float | None = None
    max_bytes: int | None = None
    max_policy_queries: int | None = None
    retry_limit: int | None = None
    per_cell_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in ("max_inference_calls", "max_policy_queries", "retry_limit", "max_bytes"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"{name} must be an integer or None")
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        for name in (
            "max_wall_time_ms",
            "max_compute_time_ms",
            "max_gpu_hours",
            "per_cell_timeout_seconds",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError(f"{name} must be a finite non-negative number or None")


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
    *,
    calls: int,
    wall_time_ms: float,
    compute_time_ms: float,
    budget: ResourceBudget,
    gpu_hours: float | None = None,
    output_bytes: int | None = None,
    policy_queries: int | None = None,
    retries: int | None = None,
) -> ResourceAudit:
    violations: list[str] = []
    if budget.max_inference_calls is not None and calls > budget.max_inference_calls:
        violations.append("inference_call_budget_exceeded")
    if budget.max_wall_time_ms is not None and wall_time_ms > budget.max_wall_time_ms:
        violations.append("wall_time_budget_exceeded")
    if budget.max_compute_time_ms is not None and compute_time_ms > budget.max_compute_time_ms:
        violations.append("compute_time_budget_exceeded")
    if budget.max_gpu_hours is not None:
        if gpu_hours is None:
            violations.append("gpu_hours_unavailable")
        elif gpu_hours > budget.max_gpu_hours:
            violations.append("gpu_hours_budget_exceeded")
    if budget.max_bytes is not None:
        if output_bytes is None:
            violations.append("output_bytes_unavailable")
        elif output_bytes > budget.max_bytes:
            violations.append("output_bytes_budget_exceeded")
    if budget.max_policy_queries is not None:
        measured_queries = calls if policy_queries is None else policy_queries
        if measured_queries > budget.max_policy_queries:
            violations.append("policy_query_budget_exceeded")
    if budget.retry_limit is not None and retries is not None and retries > budget.retry_limit:
        violations.append("retry_budget_exceeded")
    if budget.per_cell_timeout_seconds is not None:
        if wall_time_ms / 1000.0 > budget.per_cell_timeout_seconds:
            violations.append("per_cell_timeout_exceeded")
    return ResourceAudit(not violations, tuple(violations))
