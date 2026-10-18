"""Dependency-free AlpaBridge route-follower trajectory primitives."""

from __future__ import annotations

import math
import os
from typing import Any


def ramped_distances(
    times_s: Any,
    *,
    speed_mps: float,
    target_speed_mps: float,
    accel_mps2: float,
):
    """Distance along a route under a capped linear speed ramp."""
    import numpy as np

    v0 = max(0.0, speed_mps)
    if target_speed_mps <= 0.0 or accel_mps2 <= 0.0 or abs(target_speed_mps - v0) < 1e-9:
        return times_s * v0
    vt = max(0.0, target_speed_mps)
    acceleration = accel_mps2 if vt > v0 else -accel_mps2
    ramp_time = (vt - v0) / acceleration
    ramp = times_s <= ramp_time
    distances = np.empty_like(times_s)
    distances[ramp] = v0 * times_s[ramp] + 0.5 * acceleration * times_s[ramp] ** 2
    ramp_end_distance = v0 * ramp_time + 0.5 * acceleration * ramp_time**2
    distances[~ramp] = ramp_end_distance + vt * (times_s[~ramp] - ramp_time)
    return distances


def ramp_settings() -> tuple[float, float]:
    """Read the source driver ramp knobs; invalid values disable safely."""
    try:
        target = float(os.environ.get("ALPABRIDGE_RF_TARGET_SPEED_MPS", "0") or 0.0)
    except ValueError:
        target = 0.0
    try:
        acceleration = float(os.environ.get("ALPABRIDGE_RF_ACCEL_MPS2", "1.5") or 1.5)
    except ValueError:
        acceleration = 1.5
    if not (math.isfinite(target) and math.isfinite(acceleration)):
        return 0.0, 1.5
    return max(0.0, target), max(0.0, acceleration)


def ramp_scale() -> float:
    """Return the positive per-scene warmup-speed multiplier, or zero."""
    try:
        scale = float(os.environ.get("ALPABRIDGE_RF_TARGET_SPEED_SCALE", "0") or 0.0)
    except ValueError:
        return 0.0
    if not math.isfinite(scale) or scale <= 0.0:
        return 0.0
    return scale


def effective_ramp_target_mps(
    reference_speed_mps: float | None,
    *,
    target_speed_mps: float,
    scale: float,
) -> float:
    """Combine an absolute target with the scaled per-scene reference."""
    scaled = 0.0
    if scale > 0.0 and reference_speed_mps and math.isfinite(reference_speed_mps):
        scaled = scale * max(0.0, reference_speed_mps)
    if scaled <= 0.0:
        return target_speed_mps
    if target_speed_mps <= 0.0:
        return scaled
    return min(target_speed_mps, scaled)


def ramp_up_only(target_speed_mps: float, *, current_speed_mps: float) -> float:
    """Disable a target at/below launch speed instead of applying braking."""
    if 0.0 < target_speed_mps <= max(0.0, current_speed_mps):
        return 0.0
    return target_speed_mps


def sample_route(
    points: list[tuple[float, float]],
    *,
    speed_mps: float,
    horizon_seconds: float,
    point_count: int,
    target_speed_override_mps: float | None = None,
):
    """Sample a route with the source driver’s disabled-by-default ramp."""
    import numpy as np

    segment_lengths = [
        math.dist(points[index], points[index + 1]) for index in range(len(points) - 1)
    ]
    total_length = sum(segment_lengths)
    if total_length <= 1e-6:
        return straight_trajectory(
            speed_mps=speed_mps,
            horizon_seconds=horizon_seconds,
            point_count=point_count,
        )
    cumulative = [0.0]
    for length in segment_lengths:
        cumulative.append(cumulative[-1] + length)
    times_s = np.linspace(
        horizon_seconds / point_count, horizon_seconds, point_count, dtype=np.float64
    )
    target_speed, acceleration = ramp_settings()
    if target_speed_override_mps is not None:
        target_speed = target_speed_override_mps
    target_distances = ramped_distances(
        times_s,
        speed_mps=speed_mps,
        target_speed_mps=target_speed,
        accel_mps2=acceleration,
    ).astype(np.float32)
    samples = [
        point_at_distance(points, cumulative, float(distance)) for distance in target_distances
    ]
    return np.asarray(samples, dtype=np.float32)


def point_at_distance(
    points: list[tuple[float, float]], cumulative: list[float], distance_m: float
) -> tuple[float, float]:
    if distance_m <= 0.0:
        return points[0]
    total_length = cumulative[-1]
    if distance_m >= total_length:
        start, end = points[-2], points[-1]
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = max(1e-6, math.hypot(dx, dy))
        extra = distance_m - total_length
        return end[0] + extra * dx / length, end[1] + extra * dy / length
    for index in range(len(cumulative) - 1):
        if cumulative[index + 1] < distance_m:
            continue
        start, end = points[index], points[index + 1]
        length = max(1e-6, cumulative[index + 1] - cumulative[index])
        alpha = (distance_m - cumulative[index]) / length
        return start[0] + alpha * (end[0] - start[0]), start[1] + alpha * (end[1] - start[1])
    return points[-1]


def straight_trajectory(*, speed_mps: float, horizon_seconds: float, point_count: int):
    import numpy as np

    times = np.linspace(
        horizon_seconds / point_count, horizon_seconds, point_count, dtype=np.float32
    )
    x = times * max(0.0, speed_mps)
    return np.stack((x, np.zeros_like(x)), axis=1).astype(np.float32)


def segment_point_distance(
    start: tuple[float, float], end: tuple[float, float], point: tuple[float, float]
) -> float:
    """Return the 2-D distance to a segment with a clamped projection."""
    segment = (end[0] - start[0], end[1] - start[1])
    length_squared = segment[0] * segment[0] + segment[1] * segment[1]
    if length_squared == 0.0:
        return math.dist(start, point)
    offset = (point[0] - start[0], point[1] - start[1])
    projection = (offset[0] * segment[0] + offset[1] * segment[1]) / length_squared
    projection = min(1.0, max(0.0, projection))
    nearest = (
        start[0] + segment[0] * projection,
        start[1] + segment[1] * projection,
    )
    return math.dist(nearest, point)


def distance_to_polyline(point: tuple[float, float], polyline: list[tuple[float, float]]) -> float:
    """Return perpendicular distance to the nearest clamped polyline segment."""
    return min(
        segment_point_distance(polyline[index], polyline[index + 1], point)
        for index in range(len(polyline) - 1)
    )
