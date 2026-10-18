"""Dependency-free measurement hooks for execution-time resource evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Callable

ResourceSampler = Callable[[], Mapping[str, Any]]


def sample_resources(sampler: ResourceSampler | None) -> dict[str, float | int | str]:
    """Read and validate a sampler without silently accepting NaN telemetry."""
    if sampler is None:
        return {}
    try:
        raw = sampler()
    except Exception as exc:
        return {"sample_error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(raw, Mapping):
        return {"sample_error": "resource sampler must return a mapping"}
    result: dict[str, float | int | str] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not name:
            return {"sample_error": "resource metric names must be non-empty strings"}
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return {"sample_error": f"resource metric {name} must be numeric"}
        if not math.isfinite(float(value)) or value < 0:
            return {"sample_error": f"resource metric {name} must be finite and non-negative"}
        result[name] = value
    return result


def delta_resources(
    before: Mapping[str, float | int | str], after: Mapping[str, float | int | str]
) -> dict[str, float | int | str]:
    """Compute counter deltas while preserving gauges and sampling errors."""
    if "sample_error" in before or "sample_error" in after:
        return {"sample_error": str(after.get("sample_error") or before.get("sample_error"))}
    metrics: dict[str, float | int | str] = {}
    for name in sorted(set(before) | set(after)):
        left = before.get(name)
        right = after.get(name)
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            metrics[name] = "missing_boundary"
            continue
        if name.endswith(("_count", "_calls", "_ms")):
            delta = right - left
            metrics[name] = delta if delta >= 0 else "counter_reset"
        else:
            metrics[name] = right
    return metrics
