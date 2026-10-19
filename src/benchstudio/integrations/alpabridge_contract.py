"""Source-backed AlpaSim/AlpaBridge prediction and sensor contracts."""

from __future__ import annotations

import math
import zlib
from typing import Any

import numpy as np


def make_model_prediction(trajectory_xy: np.ndarray, headings: np.ndarray, reasoning_text: str | None = None) -> Any:
    """Convert flat planar policy output to the current candidate tensor shape."""
    positions_xy = np.asarray(trajectory_xy, dtype=np.float64).reshape(-1, 2)
    yaw = np.asarray(headings, dtype=np.float64).reshape(-1)
    if positions_xy.shape[0] < 1:
        raise ValueError("prediction trajectory must contain at least one point")
    if yaw.shape != (positions_xy.shape[0],):
        raise ValueError("prediction headings must contain one value per trajectory point")
    positions = np.zeros((1, positions_xy.shape[0], 3), dtype=np.float64)
    positions[0, :, :2] = positions_xy
    rotations = np.zeros((1, yaw.shape[0], 3, 3), dtype=np.float64)
    rotations[0, :, 0, 0] = np.cos(yaw)
    rotations[0, :, 0, 1] = -np.sin(yaw)
    rotations[0, :, 1, 0] = np.sin(yaw)
    rotations[0, :, 1, 1] = np.cos(yaw)
    rotations[0, :, 2, 2] = 1.0
    return ModelPredictionStub(positions, rotations, reasoning_text=reasoning_text)


class ModelPredictionStub:
    """Dependency-free stand-in matching the current AlpaSim prediction fields."""

    def __init__(self, candidate_positions: np.ndarray, candidate_rotations: np.ndarray, selected_index: int = 0, reasoning_text: str | None = None) -> None:
        self.candidate_positions = candidate_positions
        self.candidate_rotations = candidate_rotations
        self.selected_index = selected_index
        self.reasoning_text = reasoning_text


def prediction_trajectory_xy(prediction: Any) -> np.ndarray:
    if hasattr(prediction, "candidate_positions"):
        positions = np.asarray(prediction.candidate_positions, dtype=np.float64)
        return positions[int(getattr(prediction, "selected_index", 0) or 0)][:, :2]
    return np.asarray(prediction.trajectory_xy, dtype=np.float64).reshape(-1, 2)


def prediction_headings(prediction: Any) -> np.ndarray:
    if hasattr(prediction, "candidate_rotations"):
        rotations = np.asarray(prediction.candidate_rotations, dtype=np.float64)
        selected = rotations[int(getattr(prediction, "selected_index", 0) or 0)]
        return np.arctan2(selected[:, 1, 0], selected[:, 0, 0])
    return np.asarray(prediction.headings, dtype=np.float64).reshape(-1)


def resample_trajectory(trajectory_xy: np.ndarray, output_frequency_hz: int, horizon_seconds: float, source_timestamps: np.ndarray | None = None) -> np.ndarray:
    output_frequency = float(output_frequency_hz)
    horizon = float(horizon_seconds)
    if not math.isfinite(output_frequency) or output_frequency <= 0:
        raise ValueError("output_frequency_hz must be positive and finite")
    if not math.isfinite(horizon) or horizon <= 0:
        raise ValueError("horizon_seconds must be positive and finite")
    trajectory = np.asarray(trajectory_xy, dtype=np.float32)
    if trajectory.ndim != 2 or trajectory.shape[1] != 2 or trajectory.shape[0] < 1 or not np.isfinite(trajectory).all():
        raise ValueError("trajectory_xy must have shape (N, 2) with finite values")
    expected_points = max(1, int(round(output_frequency * horizon)))
    target_t = np.linspace(horizon / expected_points, horizon, expected_points, dtype=np.float64)
    if source_timestamps is None:
        source_t = np.linspace(0.0, horizon, trajectory.shape[0] + 1, dtype=np.float64)
        matches = expected_points == trajectory.shape[0]
    else:
        timestamps = np.asarray(source_timestamps, dtype=np.float64)
        if timestamps.shape != (trajectory.shape[0],) or not np.isfinite(timestamps).all() or np.any(timestamps <= 0) or np.any(timestamps > horizon) or np.any(np.diff(timestamps) <= 0):
            raise ValueError("source_timestamps must be strictly increasing within (0, horizon_seconds]")
        source_t = np.concatenate((np.array([0.0]), timestamps))
        matches = expected_points == trajectory.shape[0] and np.allclose(timestamps, target_t, rtol=0, atol=1e-7)
    if matches:
        return trajectory
    source_xy = np.vstack((np.zeros((1, 2), dtype=np.float32), trajectory))
    return np.stack((np.interp(target_t, source_t, source_xy[:, 0]), np.interp(target_t, source_t, source_xy[:, 1])), axis=1).astype(np.float32)


def _pose_signature(pose: Any) -> tuple[float, float, float] | None:
    pose = getattr(pose, "pose", pose)
    def attr(obj: Any, names: tuple[str, ...]) -> float | None:
        for name in names:
            value = getattr(obj, name, None)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    pass
        return None
    x, y = attr(pose, ("x", "world_x")), attr(pose, ("y", "world_y"))
    vec = getattr(pose, "vec", None)
    if x is None and vec is not None: x = attr(vec, ("x",))
    if y is None and vec is not None: y = attr(vec, ("y",))
    if x is None or y is None: return None
    yaw = attr(pose, ("yaw", "heading", "heading_rad", "world_heading"))
    if yaw is None:
        quat = getattr(pose, "quat", getattr(pose, "quaternion", None))
        w, qx, qy, qz = (attr(quat, (name,)) for name in ("w", "x", "y", "z"))
        w, qx, qy, qz = (1.0 if value is None else value for value in (w, qx, qy, qz))
        yaw = math.atan2(2 * (w * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))
    return round(x, 4), round(y, 4), round(yaw, 6)


def pose_xy_yaw(pose: Any) -> tuple[float, float, float] | None:
    return _pose_signature(pose)


def pose_history_speed_mps(ego_pose_history: Any) -> float | None:
    parsed = []
    for pose in list(ego_pose_history or []):
        signature = _pose_signature(pose)
        timestamp = getattr(pose, "timestamp_us", None)
        if signature is not None and timestamp is not None:
            try: parsed.append((int(timestamp), signature[0], signature[1]))
            except (TypeError, ValueError): pass
    if len(parsed) < 2: return None
    t0, x0, y0 = parsed[-2]; t1, x1, y1 = parsed[-1]
    dt_s = (t1 - t0) / 1_000_000
    return None if dt_s <= 1e-6 else float(math.hypot(x1 - x0, y1 - y0) / dt_s)


def corrected_speed_mps(prediction_input: Any, *, zero_threshold_mps: float = 0.1, motion_threshold_mps: float = 0.5) -> float:
    reported = max(0.0, float(getattr(prediction_input, "speed", 0.0) or 0.0))
    pose_speed = pose_history_speed_mps(getattr(prediction_input, "ego_pose_history", None))
    return pose_speed if reported < zero_threshold_mps and pose_speed is not None and pose_speed >= motion_threshold_mps else reported


def camera_fingerprint(prediction_input: Any) -> int | None:
    fingerprint = None
    for camera_id in sorted((getattr(prediction_input, "camera_images", {}) or {})):
        frames = (getattr(prediction_input, "camera_images", {}) or {}).get(camera_id) or []
        if not frames: continue
        frame = frames[-1]; image = getattr(frame, "image", frame[1] if isinstance(frame, (tuple, list)) and len(frame) >= 2 else None)
        if image is None: continue
        array = np.ascontiguousarray(np.asarray(image))
        value = zlib.crc32(camera_id.encode())
        value = zlib.crc32(str(array.shape).encode(), value)
        value = zlib.crc32(str(array.dtype).encode(), value)
        value = zlib.crc32(memoryview(array).cast("B"), value)
        fingerprint = value if fingerprint is None else zlib.crc32(value.to_bytes(4, "little"), fingerprint)
    return fingerprint
