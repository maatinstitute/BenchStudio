from types import SimpleNamespace

from ival.integrations.alpabridge_signal import (
    dynamics_risk,
    filtered_route_points,
    route_waypoints_from_input,
    structured_hazards_from_input,
    visibility_risk_from_cameras,
)


def test_route_filter_matches_signal_boundary():
    value = SimpleNamespace(route_waypoints=[{"x": -10, "y": 0}, {"x": 0.1, "y": 0}, {"x": 10, "y": 2}])
    assert route_waypoints_from_input(value)[-1]["x"] == 10
    assert filtered_route_points(route_waypoints_from_input(value)) == [(0.0, 0.0), (10.0, 2.0)]


def test_hazard_normalization_drops_non_finite_values():
    value = SimpleNamespace(structured_hazards=[{"x": 4, "y": 1, "radius": 1, "label": "car"}, {"x": float("nan")}])
    hazards = structured_hazards_from_input(value)
    assert hazards == [{"x": 4.0, "y": 1.0, "radius": 1.0, "vx": 0.0, "vy": 0.0, "kind": "signal_hazard", "label": "car"}]


def test_risk_boundaries_are_stable():
    assert dynamics_risk(0.0, 0.0) == 1.0
    assert dynamics_risk(3.0, 0.0) == 0.0
    assert visibility_risk_from_cameras({}) == 0.0


def test_visibility_risk_uses_latest_camera_frame():
    import numpy as np

    frame = SimpleNamespace(image=np.zeros((2, 2, 3), dtype=np.uint8))
    assert visibility_risk_from_cameras({"front": [frame]}) == 1.0
