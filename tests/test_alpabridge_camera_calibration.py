from __future__ import annotations

from types import SimpleNamespace

import pytest

from ival.integrations import (
    CameraCalibration,
    calibration_from_available_camera,
    calibrations_from_session_request,
)


def _pinhole_camera(
    logical_id: str = "camera_front_wide_120fov",
    *,
    width: int = 1920,
    height: int = 1080,
) -> SimpleNamespace:
    return SimpleNamespace(
        logical_id=logical_id,
        intrinsics=SimpleNamespace(
            logical_id=logical_id,
            resolution_w=width,
            resolution_h=height,
            opencv_pinhole_param=SimpleNamespace(
                principal_point_x=960.0,
                principal_point_y=540.0,
                focal_length_x=1545.0,
                focal_length_y=1545.0,
            ),
        ),
    )


def _ftheta_camera(logical_id: str = "camera_cross_left_120fov") -> SimpleNamespace:
    return SimpleNamespace(
        logical_id=logical_id,
        intrinsics=SimpleNamespace(
            logical_id=logical_id,
            resolution_w=1920,
            resolution_h=1080,
            ftheta_param=SimpleNamespace(
                principal_point_x=958.0,
                principal_point_y=542.0,
            ),
        ),
    )


def test_pinhole_intrinsics_are_read_from_the_camera_spec() -> None:
    calibration = calibration_from_available_camera(_pinhole_camera())

    assert calibration is not None
    assert calibration.model == "opencv_pinhole"
    assert calibration.width == 1920
    assert calibration.height == 1080
    assert calibration.principal_point_x == 960.0
    assert calibration.focal_length_x == 1545.0


def test_ftheta_intrinsics_are_read_without_a_focal_length() -> None:
    calibration = calibration_from_available_camera(_ftheta_camera())

    assert calibration is not None
    assert calibration.model == "ftheta"
    assert calibration.principal_point_y == 542.0
    assert calibration.focal_length_x is None


def test_scaling_moves_pixel_terms_on_each_axis() -> None:
    calibration = calibration_from_available_camera(_pinhole_camera())
    assert calibration is not None

    scaled = calibration.scaled_to(1916, 1080)

    assert scaled.width == 1916
    assert scaled.height == 1080
    assert scaled.principal_point_x == pytest.approx(960.0 * 1916 / 1920)
    assert scaled.principal_point_y == 540.0
    assert scaled.focal_length_x == pytest.approx(1545.0 * 1916 / 1920)
    assert scaled.focal_length_y == 1545.0
    assert scaled.model == calibration.model


def test_scaling_to_declared_size_is_identity() -> None:
    calibration = calibration_from_available_camera(_pinhole_camera())
    assert calibration is not None
    assert calibration.scaled_to(1920, 1080) is calibration


@pytest.mark.parametrize("size", [(0, 1080), (1920, 0), (-1, 100)])
def test_scaling_rejects_unusable_target_size(size: tuple[int, int]) -> None:
    calibration = calibration_from_available_camera(_pinhole_camera())
    assert calibration is not None
    with pytest.raises(ValueError):
        calibration.scaled_to(*size)


def test_camera_without_resolution_or_known_model_is_skipped() -> None:
    assert calibration_from_available_camera(_pinhole_camera(width=0, height=0)) is None
    unknown = SimpleNamespace(
        logical_id="camera_front_tele_30fov",
        intrinsics=SimpleNamespace(
            logical_id="camera_front_tele_30fov", resolution_w=1920, resolution_h=1080
        ),
    )
    assert calibration_from_available_camera(unknown) is None


def test_session_request_yields_one_calibration_per_usable_camera() -> None:
    request = SimpleNamespace(
        rollout_spec=SimpleNamespace(
            vehicle=SimpleNamespace(
                available_cameras=[
                    _pinhole_camera(),
                    _ftheta_camera(),
                    _pinhole_camera("camera_broken", width=0, height=0),
                ]
            )
        )
    )
    calibrations = calibrations_from_session_request(request)
    assert set(calibrations) == {"camera_front_wide_120fov", "camera_cross_left_120fov"}
    assert isinstance(calibrations["camera_front_wide_120fov"], CameraCalibration)


def test_session_without_rollout_spec_yields_nothing() -> None:
    assert calibrations_from_session_request(SimpleNamespace()) == {}
