"""Fail-closed SmolVLA driving manifest and trajectory contracts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from .alpabridge_contract import make_model_prediction

SMOLVLA_DRIVING_SCHEMA_VERSION = "smolvla-driving-v1"
TARGET_REPRESENTATION = "ego_frame_positions_xy"


def validate_manifest_row(row: Mapping[str, Any]) -> None:
    _require_mapping(row, "row")
    _require_exact(row, "schema_version", SMOLVLA_DRIVING_SCHEMA_VERSION)
    _require_sha256(row, "sample_id")
    _require_nonempty_string(row, "scene_id")
    _require_mapping(row.get("observation"), "observation")
    _require_mapping(row.get("target"), "target")
    _require_mapping(row.get("provenance"), "provenance")
    observation, target, provenance = row["observation"], row["target"], row["provenance"]
    cameras = observation.get("cameras")
    if not isinstance(cameras, Sequence) or isinstance(cameras, (str, bytes)) or len(cameras) != 4:
        raise ValueError("observation.cameras must contain exactly four camera records")
    camera_ids: set[str] = set()
    for camera in cameras:
        _require_mapping(camera, "observation.cameras[]")
        camera_id = _nonempty_string(camera.get("camera_id"), "camera_id")
        if camera_id in camera_ids:
            raise ValueError(f"duplicate camera_id {camera_id!r}")
        camera_ids.add(camera_id)
        for key in ("timestamp_us", "decoded_width", "decoded_height"):
            _require_positive_int(camera, key)
        for key in ("frame_sha256", "calibration_sha256", "preprocessing_sha256"):
            _require_sha256(camera, key)
    for key in ("ego_pose_history_sha256", "route_waypoints_sha256"):
        _require_sha256(observation, key)
    _require_exact(observation, "coordinate_frame", "current_rig")
    _require_exact(target, "representation", TARGET_REPRESENTATION)
    trajectory_to_model_prediction(target.get("positions_xy"), target.get("timestamps_s"))
    _require_sha256(target, "generation_code_sha256")
    _require_sha256(provenance, "source_record_sha256")
    _require_nonempty_string(provenance, "split")
    if provenance.get("split") not in {"train", "development", "test"}:
        raise ValueError("provenance.split must be train, development, or test")
    _require_nonempty_string(provenance, "ancestry_id")
    forbidden = {"episode_outcome", "recorded_future", "evaluation_ground_truth"}
    present = forbidden.intersection(observation) | forbidden.intersection(target)
    if present:
        raise ValueError(f"manifest row contains forbidden inference signal(s): {sorted(present)}")


def trajectory_to_model_prediction(positions_xy: Any, timestamps_s: Any) -> Any:
    positions = np.asarray(positions_xy, dtype=np.float64)
    timestamps = np.asarray(timestamps_s, dtype=np.float64)
    if positions.ndim != 2 or positions.shape[0] < 2 or positions.shape[1] != 2:
        raise ValueError("positions_xy must have shape (T, 2) with T >= 2")
    if timestamps.shape != (positions.shape[0],):
        raise ValueError("timestamps_s must contain one timestamp per trajectory point")
    if not np.isfinite(positions).all() or not np.isfinite(timestamps).all():
        raise ValueError("trajectory positions and timestamps must be finite")
    if timestamps[0] <= 0 or not np.all(np.diff(timestamps) > 0):
        raise ValueError("timestamps_s must be strictly increasing and start after t=0")
    deltas = np.diff(np.vstack((np.zeros((1, 2)), positions)), axis=0)
    headings = np.arctan2(deltas[:, 1], deltas[:, 0])
    if not np.isfinite(headings).all():
        raise ValueError("trajectory headings are not finite")
    return make_model_prediction(positions, headings)


def _require_mapping(value: Any, name: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")


def _require_exact(mapping: Mapping[str, Any], key: str, expected: str) -> None:
    if mapping.get(key) != expected:
        raise ValueError(f"{key} must equal {expected!r}")


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_nonempty_string(mapping: Mapping[str, Any], key: str) -> None:
    _nonempty_string(mapping.get(key), key)


def _require_positive_int(mapping: Mapping[str, Any], key: str) -> None:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")


def _require_sha256(mapping: Mapping[str, Any], key: str) -> None:
    value = mapping.get(key)
    if not isinstance(value, str) or len(value) != hashlib.sha256().digest_size * 2:
        raise ValueError(f"{key} must be a SHA256 hexadecimal digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{key} must be a SHA256 hexadecimal digest") from exc
