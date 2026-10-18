from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Frame:
    t_ms: int
    joints: dict[str, float]
    objects: dict[str, dict[str, list[float]]]


def load_trajectory(path: Path) -> list[Frame]:
    """Load and merge robot-joint/object streams into time-ordered frames."""
    frames: dict[int, Frame] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        t_ms = record.get("t_ms")
        state = record.get("state")
        if not isinstance(t_ms, int) or not isinstance(state, dict):
            continue
        frame = frames.setdefault(t_ms, Frame(t_ms=t_ms, joints={}, objects={}))
        if record.get("stream") == "robot_joints":
            positions = state.get("joint_positions")
            if isinstance(positions, dict):
                frame.joints.update({str(k): float(v) for k, v in positions.items()})
        elif record.get("stream") == "objects":
            for object_id, pose in state.items():
                if isinstance(pose, dict) and "position_xyz" in pose:
                    frame.objects[str(object_id)] = pose
    return [frames[timestamp] for timestamp in sorted(frames)]


def compare_trajectories(
    path_a: Path,
    path_b: Path,
    *,
    position_split_m: float = 0.01,
    joint_split_rad: float = 0.05,
    max_series_points: int = 200,
) -> dict[str, Any] | None:
    """Time-align two traces and localize their first meaningful divergence."""
    frames_a = load_trajectory(path_a) if path_a.is_file() else []
    frames_b = load_trajectory(path_b) if path_b.is_file() else []
    if not frames_a or not frames_b:
        return None
    by_time_b = {frame.t_ms: frame for frame in frames_b}
    tolerance = max(1.0, _median_step_ms([frame.t_ms for frame in frames_a]) / 2.0)
    pairs = _align([frame.t_ms for frame in frames_a], list(by_time_b), tolerance)
    frame_by_time_a = {frame.t_ms: frame for frame in frames_a}
    series: list[dict[str, Any]] = []
    split: dict[str, Any] | None = None
    max_joint = max_position = max_rotation = 0.0
    for time_a, time_b in pairs:
        frame_a = frame_by_time_a[time_a]
        frame_b = by_time_b[time_b]
        joint_rmse = _joint_rmse(frame_a.joints, frame_b.joints)
        position_delta, rotation_delta = _object_deltas(frame_a.objects, frame_b.objects)
        if joint_rmse is None and position_delta is None:
            continue
        sample = {
            "t_ms": time_a,
            "joint_rmse_rad": joint_rmse,
            "object_position_delta_m": position_delta,
            "object_rotation_delta_rad": rotation_delta,
        }
        series.append(sample)
        max_joint = max(max_joint, joint_rmse or 0.0)
        max_position = max(max_position, position_delta or 0.0)
        max_rotation = max(max_rotation, rotation_delta or 0.0)
        if split is None:
            if position_delta is not None and position_delta > position_split_m:
                split = {"t_ms": time_a, "metric": "object_position_delta_m", "value": position_delta, "threshold": position_split_m}
            elif joint_rmse is not None and joint_rmse > joint_split_rad:
                split = {"t_ms": time_a, "metric": "joint_rmse_rad", "value": joint_rmse, "threshold": joint_split_rad}
    if not series:
        return None
    final = series[-1]
    return {
        "schema": "benchstudio_trajectory_divergence_v1",
        "compared_frames": len(series),
        "duration_ms": final["t_ms"],
        "joint_rmse_rad": {"max": max_joint, "final": final["joint_rmse_rad"]},
        "object_position_delta_m": {"max": max_position, "final": final["object_position_delta_m"]},
        "object_rotation_delta_rad": {"max": max_rotation, "final": final["object_rotation_delta_rad"]},
        "split": split,
        "series": _downsample(series, max_series_points),
    }


def _align(times_a: list[int], times_b: list[int], tolerance: float) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    index_b = 0
    for time_a in times_a:
        while index_b + 1 < len(times_b) and abs(times_b[index_b + 1] - time_a) <= abs(times_b[index_b] - time_a):
            index_b += 1
        if times_b and abs(times_b[index_b] - time_a) <= tolerance:
            pairs.append((time_a, times_b[index_b]))
    return pairs


def _median_step_ms(times: list[int]) -> float:
    if len(times) < 2:
        return 1.0
    steps = sorted(times[index + 1] - times[index] for index in range(len(times) - 1))
    middle = len(steps) // 2
    return float(steps[middle]) if len(steps) % 2 else (steps[middle - 1] + steps[middle]) / 2.0


def _joint_rmse(joints_a: dict[str, float], joints_b: dict[str, float]) -> float | None:
    shared = sorted(set(joints_a) & set(joints_b))
    if not shared:
        return None
    return math.sqrt(sum((joints_a[name] - joints_b[name]) ** 2 for name in shared) / len(shared))


def _object_deltas(objects_a: dict[str, dict[str, list[float]]], objects_b: dict[str, dict[str, list[float]]]) -> tuple[float | None, float | None]:
    shared = sorted(set(objects_a) & set(objects_b))
    if not shared:
        return None, None
    max_position = max_rotation = 0.0
    for object_id in shared:
        pose_a, pose_b = objects_a[object_id], objects_b[object_id]
        max_position = max(max_position, math.sqrt(sum((a - b) ** 2 for a, b in zip(pose_a["position_xyz"], pose_b["position_xyz"]))))
        quat_a, quat_b = pose_a.get("quat_wxyz"), pose_b.get("quat_wxyz")
        if quat_a and quat_b:
            dot = abs(sum(a * b for a, b in zip(quat_a, quat_b)))
            max_rotation = max(max_rotation, 2.0 * math.acos(min(1.0, max(-1.0, dot))))
    return max_position, max_rotation


def _downsample(series: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    if maximum < 1:
        raise ValueError("max_series_points must be positive")
    if len(series) <= maximum:
        return series
    stride = math.ceil(len(series) / maximum)
    sampled = series[::stride]
    if sampled[-1] != series[-1]:
        sampled.append(series[-1])
    return sampled
