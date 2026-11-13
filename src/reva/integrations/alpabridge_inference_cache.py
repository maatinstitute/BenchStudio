"""Source-backed pose-reanchored inference throttling for AlpaBridge policies."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np


def _first_float_attr(obj: Any, names: tuple[str, ...]) -> float | None:
    for name in names:
        value = getattr(obj, name, None)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _yaw_from_quat_like(quat: Any) -> float:
    w = _first_float_attr(quat, ("w",))
    x = _first_float_attr(quat, ("x",))
    y = _first_float_attr(quat, ("y",))
    z = _first_float_attr(quat, ("z",))
    w, x, y, z = (1.0 if value is None else value for value in (w, x, y, z))
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def _pose_like_to_signature(pose: Any) -> tuple[float, float, float] | None:
    raw_pose = getattr(pose, "pose", None)
    if raw_pose is not None:
        pose = raw_pose
    x = _first_float_attr(pose, ("x", "world_x"))
    y = _first_float_attr(pose, ("y", "world_y"))
    vec = getattr(pose, "vec", None)
    if x is None and vec is not None:
        x = _first_float_attr(vec, ("x",))
    if y is None and vec is not None:
        y = _first_float_attr(vec, ("y",))
    position = getattr(pose, "position", None)
    if x is None and position is not None:
        x = _first_float_attr(position, ("x",))
    if y is None and position is not None:
        y = _first_float_attr(position, ("y",))
    translation = getattr(pose, "translation", None)
    if x is None and translation is not None:
        x = _first_float_attr(translation, ("x",))
    if y is None and translation is not None:
        y = _first_float_attr(translation, ("y",))
    if x is None or y is None:
        return None
    yaw = _first_float_attr(pose, ("yaw", "heading", "heading_rad", "world_heading"))
    if yaw is None:
        yaw = _yaw_from_quat_like(getattr(pose, "quat", getattr(pose, "quaternion", None)))
    return (round(float(x), 4), round(float(y), 4), round(float(yaw), 6))


@dataclass
class CachedInference:
    anchor_time_us: int
    origin_xy: np.ndarray
    origin_yaw: float
    relative_xy: np.ndarray


def rotate2d(vectors: np.ndarray, angle: float) -> np.ndarray:
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    rotation = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    return vectors @ rotation.T


def reanchor_trajectory(cached: CachedInference, *, current_xy: np.ndarray, current_yaw: float) -> np.ndarray:
    world_xy = cached.origin_xy + rotate2d(cached.relative_xy, cached.origin_yaw)
    return rotate2d(world_xy - current_xy, -current_yaw)


def cache_context(prediction_input: Any) -> tuple[str | None, int | None, np.ndarray | None, float | None]:
    session_uuid = getattr(prediction_input, "session_uuid", None)
    time_now_us = getattr(prediction_input, "time_now_us", None)
    ego_pose_history = getattr(prediction_input, "ego_pose_history", None) or []
    if not session_uuid or time_now_us is None or not ego_pose_history:
        return None, None, None, None
    signature = _pose_like_to_signature(ego_pose_history[-1])
    if signature is None:
        return None, None, None, None
    return str(session_uuid), int(time_now_us), np.array(signature[:2], dtype=np.float64), float(signature[2])


class PoseReanchoredInferenceCache:
    def __init__(self, min_interval_s: float) -> None:
        self._min_interval_s = float(min_interval_s)
        self._cache: dict[str, CachedInference] = {}
        self._lock = threading.Lock()

    def forget(self, session_uuid: str) -> None:
        with self._lock:
            self._cache.pop(str(session_uuid), None)

    def get(self, prediction_input: Any, infer: Callable[[], np.ndarray]) -> tuple[np.ndarray, bool]:
        session_uuid, time_now_us, current_xy, current_yaw = cache_context(prediction_input)
        with self._lock:
            cached = self._cache.get(session_uuid) if session_uuid is not None else None
        if cached is not None and (time_now_us - cached.anchor_time_us) / 1_000_000.0 < self._min_interval_s:
            return reanchor_trajectory(cached, current_xy=current_xy, current_yaw=current_yaw), True
        trajectory_xy = infer()
        if session_uuid is not None:
            with self._lock:
                self._cache[session_uuid] = CachedInference(int(time_now_us), current_xy, current_yaw, trajectory_xy)
        return trajectory_xy, False
