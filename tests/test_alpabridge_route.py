import numpy as np
import pytest

from ival.integrations import (
    distance_to_polyline,
    effective_ramp_target_mps,
    ramp_scale,
    ramp_settings,
    ramp_up_only,
    ramped_distances,
    sample_route,
    segment_point_distance,
)

TIMES = np.linspace(0.25, 5.0, 20)
ROUTE = [(float(x), 0.0) for x in range(0, 120, 4)]


def test_ramped_distances_preserves_disabled_and_closed_form_profiles():
    assert np.array_equal(
        ramped_distances(TIMES, speed_mps=3.0, target_speed_mps=0.0, accel_mps2=1.5), TIMES * 3.0
    )
    assert ramped_distances(TIMES, speed_mps=2.0, target_speed_mps=10.0, accel_mps2=2.0)[
        -1
    ] == pytest.approx(34.0)
    assert np.all(
        np.diff(ramped_distances(TIMES, speed_mps=2.0, target_speed_mps=10.0, accel_mps2=2.0)) > 0
    )
    assert ramped_distances(TIMES, speed_mps=12.0, target_speed_mps=6.0, accel_mps2=3.0)[
        -1
    ] == pytest.approx(36.0)
    assert np.allclose(
        ramped_distances(TIMES, speed_mps=7.0, target_speed_mps=7.0, accel_mps2=2.0), TIMES * 7.0
    )


def test_ramp_settings_and_scale_invalid_values_disable(monkeypatch):
    monkeypatch.delenv("ALPABRIDGE_RF_TARGET_SPEED_MPS", raising=False)
    monkeypatch.delenv("ALPABRIDGE_RF_ACCEL_MPS2", raising=False)
    assert ramp_settings() == (0.0, 1.5)
    monkeypatch.setenv("ALPABRIDGE_RF_TARGET_SPEED_MPS", "9.0")
    monkeypatch.setenv("ALPABRIDGE_RF_ACCEL_MPS2", "2.0")
    assert ramp_settings() == (9.0, 2.0)
    for raw in ("junk", "nan", "-inf", ""):
        monkeypatch.setenv("ALPABRIDGE_RF_TARGET_SPEED_MPS", raw)
        assert ramp_settings()[0] == 0.0
    monkeypatch.delenv("ALPABRIDGE_RF_TARGET_SPEED_SCALE", raising=False)
    assert ramp_scale() == 0.0
    monkeypatch.setenv("ALPABRIDGE_RF_TARGET_SPEED_SCALE", "2.0")
    assert ramp_scale() == 2.0
    for raw in ("junk", "nan", "-1", ""):
        monkeypatch.setenv("ALPABRIDGE_RF_TARGET_SPEED_SCALE", raw)
        assert ramp_scale() == 0.0


def test_sample_route_and_effective_target_preserve_source_semantics(monkeypatch):
    monkeypatch.setenv("ALPABRIDGE_RF_TARGET_SPEED_MPS", "0")
    locked = sample_route(ROUTE, speed_mps=2.0, horizon_seconds=5.0, point_count=20)
    monkeypatch.setenv("ALPABRIDGE_RF_TARGET_SPEED_MPS", "9.0")
    ramped = sample_route(ROUTE, speed_mps=2.0, horizon_seconds=5.0, point_count=20)
    assert ramped[-1, 0] > locked[-1, 0] * 2
    monkeypatch.delenv("ALPABRIDGE_RF_TARGET_SPEED_MPS", raising=False)
    assert np.allclose(
        sample_route(ROUTE, speed_mps=4.0, horizon_seconds=5.0, point_count=20)[:, 0],
        np.linspace(0.25, 5.0, 20) * 4.0,
        atol=1e-4,
    )
    assert effective_ramp_target_mps(5.0, target_speed_mps=0.0, scale=0.0) == 0.0
    assert effective_ramp_target_mps(3.7, target_speed_mps=0.0, scale=2.0) == pytest.approx(7.4)
    assert effective_ramp_target_mps(1.2, target_speed_mps=9.0, scale=2.0) == pytest.approx(2.4)
    assert effective_ramp_target_mps(8.5, target_speed_mps=9.0, scale=2.0) == pytest.approx(9.0)
    assert effective_ramp_target_mps(float("nan"), target_speed_mps=9.0, scale=2.0) == 9.0


def test_ramp_up_only_never_brakes():
    assert ramp_up_only(9.0, current_speed_mps=20.0) == 0.0
    assert ramp_up_only(9.0, current_speed_mps=9.0) == 0.0
    assert ramp_up_only(9.0, current_speed_mps=2.0) == 9.0
    assert ramp_up_only(0.0, current_speed_mps=5.0) == 0.0


def test_polyline_distance_uses_clamped_segments_and_handles_degenerate_waypoints():
    polyline = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    assert segment_point_distance(polyline[0], polyline[1], (4.0, 3.0)) == pytest.approx(3.0)
    assert distance_to_polyline((4.0, 3.0), polyline) == pytest.approx(3.0)
    assert distance_to_polyline((20.0, 0.0), [(0.0, 0.0), (10.0, 0.0)]) == pytest.approx(10.0)
    repeated = [(0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    assert distance_to_polyline((10.0, 5.0), repeated) == pytest.approx(5.0)
    assert distance_to_polyline((9.0, 5.0), polyline) == pytest.approx(1.0)
