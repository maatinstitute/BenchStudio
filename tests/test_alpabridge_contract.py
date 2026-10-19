import math
from types import SimpleNamespace

import numpy as np
import pytest

from benchstudio.integrations.alpabridge_contract import (
    corrected_speed_mps,
    make_model_prediction,
    pose_history_speed_mps,
    prediction_headings,
    prediction_trajectory_xy,
    resample_trajectory,
    SensorFreshnessGuard,
)


def test_prediction_shape_round_trip():
    prediction = make_model_prediction(np.array([[1.0, 0.0], [2.0, 1.0]]), np.array([0.0, math.pi / 2]))
    np.testing.assert_allclose(prediction_trajectory_xy(prediction), [[1, 0], [2, 1]])
    np.testing.assert_allclose(prediction_headings(prediction), [0, math.pi / 2])


def test_resampling_uses_explicit_timestamp_grid():
    result = resample_trajectory(np.array([[1, 0], [2, 0]], dtype=np.float32), 2, 1.0, np.array([0.25, 1.0]))
    np.testing.assert_allclose(result, [[4 / 3, 0], [2, 0]])


def test_corrected_speed_uses_pose_finite_difference_when_reported_speed_is_zero():
    pose = lambda t, x: SimpleNamespace(timestamp_us=t, x=x, y=0.0, yaw=0.0)
    value = corrected_speed_mps(SimpleNamespace(speed=0.0, ego_pose_history=[pose(0, 0), pose(1_000_000, 1)]))
    assert value == 1.0
    assert pose_history_speed_mps([]) is None


def test_sensor_freshness_guard_rejects_frozen_camera_after_pose_change():
    guard = SensorFreshnessGuard("test-model")
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    def value(timestamp, x):
        frame = SimpleNamespace(timestamp_us=timestamp, image=image)
        return SimpleNamespace(session_uuid="s", camera_images={"front": [frame]}, ego_pose_history=[SimpleNamespace(timestamp_us=timestamp, x=x, y=0.0, yaw=0.0)])
    assert guard.validate(value(100, 0.0))["status"] == "ok_initial"
    with pytest.raises(RuntimeError, match="frozen camera"):
        guard.validate(value(200, 1.0))
