import hashlib

import numpy as np
import pytest

from ival.integrations.alpabridge_contract import prediction_trajectory_xy
from ival.integrations.smolvla_driving_contract import SMOLVLA_DRIVING_SCHEMA_VERSION, TARGET_REPRESENTATION, trajectory_to_model_prediction, validate_manifest_row


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _row():
    cameras = [{"camera_id": f"camera-{index}", "timestamp_us": 1_000_000, "decoded_width": 1920, "decoded_height": 1080, "frame_sha256": _sha(f"frame-{index}"), "calibration_sha256": _sha(f"calibration-{index}"), "preprocessing_sha256": _sha("preprocess-v1")} for index in range(4)]
    return {"schema_version": SMOLVLA_DRIVING_SCHEMA_VERSION, "sample_id": _sha("sample"), "scene_id": "scene-001", "observation": {"cameras": cameras, "ego_pose_history_sha256": _sha("poses"), "route_waypoints_sha256": _sha("route"), "coordinate_frame": "current_rig"}, "target": {"representation": TARGET_REPRESENTATION, "positions_xy": [[1.0, 0.0], [2.0, 0.1], [3.0, 0.2]], "timestamps_s": [0.1, 0.2, 0.3], "generation_code_sha256": _sha("target-generator")}, "provenance": {"source_record_sha256": _sha("record"), "split": "train", "ancestry_id": "parent-001"}}


def test_valid_manifest_and_trajectory_conversion():
    validate_manifest_row(_row())
    prediction = trajectory_to_model_prediction(np.array([[1.0, 0.0], [2.0, 0.1]]), [0.1, 0.2])
    np.testing.assert_allclose(prediction_trajectory_xy(prediction), [[1, 0], [2, .1]])


def test_manifest_rejects_outcome_signal_and_wrong_camera_count():
    row = _row(); row["observation"]["episode_outcome"] = "success"
    with pytest.raises(ValueError, match="forbidden"):
        validate_manifest_row(row)
    row = _row(); row["observation"]["cameras"] = row["observation"]["cameras"][:3]
    with pytest.raises(ValueError, match="exactly four"):
        validate_manifest_row(row)


def test_trajectory_rejects_libero_action_chunk_and_nonmonotonic_time():
    with pytest.raises(ValueError, match=r"shape \(T, 2\)"):
        trajectory_to_model_prediction(np.zeros((50, 7)), np.arange(50) / 10 + .1)
    with pytest.raises(ValueError, match="strictly increasing"):
        trajectory_to_model_prediction([[1, 0], [2, 0]], [.2, .1])
