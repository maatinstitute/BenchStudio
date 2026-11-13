"""Dependency-light AlpaSim signal normalization.

This ports the reusable input-to-signal boundary from AlpaBridge's
``simulator/alpasim_signal.py``.  It intentionally does not construct an
AlpaSim/ReVa scenario or own simulator execution.
"""

from __future__ import annotations

import math
from typing import Any


def route_waypoints_from_input(prediction_input: Any) -> list[dict[str, float]]:
    raw = _first_present_attr(prediction_input, ("route_waypoints", "route_path", "navigation_waypoints", "route"))
    if raw is None:
        return []
    if hasattr(raw, "waypoints"):
        raw = getattr(raw, "waypoints")
    if isinstance(raw, dict):
        raw = raw.get("waypoints", raw.get("route_waypoints", []))
    if not isinstance(raw, (list, tuple)):
        try:
            raw = list(raw)
        except TypeError:
            return []
    return [waypoint for item in raw if (waypoint := _route_waypoint_from_item(item)) is not None]


def route_waypoints_from_signal(signal: dict[str, Any]) -> list[dict[str, float]]:
    raw = signal.get("route_waypoints", [])
    if not isinstance(raw, list):
        return []
    return [waypoint for item in raw if (waypoint := _route_waypoint_from_item(item)) is not None]


def filtered_route_points(route_waypoints: list[dict[str, float]]) -> list[tuple[float, float]]:
    """Apply AlpaBridge's shared usable-route filter, starting at the ego."""
    points: list[tuple[float, float]] = [(0.0, 0.0)]
    for waypoint in route_waypoints:
        x, y = float(waypoint["x"]), float(waypoint["y"])
        if x < -5.0 or math.hypot(x, y) > 140.0 or math.dist(points[-1], (x, y)) < 0.5:
            continue
        points.append((x, y))
    return points


def structured_hazards_from_input(prediction_input: Any) -> list[dict[str, float | str]]:
    raw = _first_present_attr(prediction_input, ("structured_hazards", "hazards", "traffic_hazards", "alpasignal"))
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = raw.get("hazards", raw.get("objects", []))
    if not isinstance(raw, list):
        return []
    return [hazard for index, item in enumerate(raw)
            if (hazard := _hazard_from_item(item, index)) is not None]


def visibility_risk_from_cameras(camera_images: dict[str, list[Any]]) -> float:
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - optional image dependency.
        np = None
    means: list[float] = []
    for frames in camera_images.values():
        if not frames:
            continue
        image = getattr(frames[-1], "image", None)
        if image is None:
            continue
        try:
            array = np.asarray(image) if np is not None else image
            size = int(array.size)
            mean = float(array.mean())
        except (AttributeError, TypeError, ValueError):
            continue
        if size:
            means.append(mean / 255.0)
    if not means:
        return 0.0
    brightness = sum(means) / len(means)
    return max(0.0, min(1.0, (0.35 - brightness) / 0.35))


def dynamics_risk(speed_mps: float, acceleration_mps2: float) -> float:
    braking_risk = max(0.0, min(1.0, -float(acceleration_mps2) / 4.0))
    low_speed_risk = max(0.0, min(1.0, (1.5 - float(speed_mps)) / 1.5))
    return max(braking_risk, low_speed_risk)


def _route_waypoint_from_item(item: Any) -> dict[str, float] | None:
    if isinstance(item, dict):
        x = item.get("x", item.get("forward_m", item.get("longitudinal_m")))
        y = item.get("y", item.get("left_m", item.get("lateral_m", 0.0)))
        z = item.get("z", 0.0)
    else:
        x = getattr(item, "x", getattr(item, "forward_m", getattr(item, "longitudinal_m", None)))
        y = getattr(item, "y", getattr(item, "left_m", getattr(item, "lateral_m", 0.0)))
        z = getattr(item, "z", 0.0)
    if x is None:
        return None
    values = (float(x), float(y), float(z))
    if not all(math.isfinite(value) for value in values):
        return None
    return {"x": round(values[0], 6), "y": round(values[1], 6), "z": round(values[2], 6)}


def _hazard_from_item(item: Any, index: int) -> dict[str, float | str] | None:
    def value(name: str, *aliases: str, default: Any = None) -> Any:
        names = (name, *aliases)
        if isinstance(item, dict):
            for candidate in names:
                if candidate in item:
                    return item[candidate]
        else:
            for candidate in names:
                if hasattr(item, candidate):
                    return getattr(item, candidate)
        return default

    x = value("x", "forward_m", "longitudinal_m")
    if x is None:
        return None
    y = value("y", "left_m", "lateral_m", default=0.0)
    radius = value("radius", "radius_m", "extent_m", default=1.25)
    vx = value("vx", "velocity_x_mps", "forward_velocity_mps", default=0.0)
    vy = value("vy", "velocity_y_mps", "lateral_velocity_mps", default=0.0)
    try:
        x_f, y_f, radius_f, vx_f, vy_f = map(float, (x, y, radius, vx, vy))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x_f, y_f, radius_f, vx_f, vy_f)):
        return None
    result: dict[str, float | str] = {
        "x": x_f, "y": y_f, "radius": max(0.25, radius_f), "vx": vx_f, "vy": vy_f,
        "kind": str(value("kind", "type", default="signal_hazard")),
        "label": str(value("label", "id", default=f"alpasignal_{index}")),
    }
    optional_numbers = {
        "width": ("width", "width_m"),
        "length": ("length", "length_m"),
        "heading": ("heading", "heading_rad", "yaw_rad"),
        "acceleration": ("acceleration", "acceleration_mps2", "longitudinal_acceleration_mps2"),
    }
    for output, aliases in optional_numbers.items():
        raw = value(aliases[0], *aliases[1:])
        if raw is not None:
            try:
                number = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                result[output] = max(0.25, number) if output in {"width", "length"} else number
    behavior = value("behavior", "motion_behavior", "intent")
    if behavior is not None:
        result["behavior"] = str(behavior)
    return result


def _first_present_attr(value: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None
