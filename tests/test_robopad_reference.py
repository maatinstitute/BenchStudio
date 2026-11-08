import numpy as np
import pytest

from benchstudio.integrations.robopad_reference import FixedReference


def _controller(held):
    points = {
        key: np.array([0.01, 0.02, 0.03])
        for key in (
            "start",
            "above_target",
            "grasp",
            "lift",
            "above_basket",
            "release",
            "withdraw",
        )
    }
    return FixedReference(held, points, translation_scale=[0.05] * 3, rotation_scale=[0.5] * 3)


def test_fixed_horizon_and_source_conditioning():
    for held, limit, first in ((True, 103, "lift"), (False, 156, "open")):
        reference = _controller(held)
        assert reference.stage == first
        actions = [reference.next_action([0, 0, 0], [0, 0, 0]) for _ in range(limit)]
        assert actions[0][-1] == (1 if held else -1)
        assert reference.stage is None
        with pytest.raises(StopIteration):
            reference.next_action([0, 0, 0], [0, 0, 0])


def test_action_scale_clipping_and_invalid_input_accounting():
    reference = _controller(False)
    np.testing.assert_allclose(
        reference.next_action([0, 0, 0], [1, 0, -1]), [0.2, 0.4, 0.6, 1, 0, -1, -1]
    )
    reference = _controller(True)
    with pytest.raises(ValueError):
        reference.next_action([float("nan")] * 3, [0] * 3)
    assert reference.actions == 0


def test_scale_and_waypoint_aliasing_are_rejected_or_isolated():
    reference = _controller(True)
    with pytest.raises(ValueError):
        FixedReference(
            True,
            reference.waypoints,
            translation_scale=[0.1] * 3,
            rotation_scale=[0.5] * 3,
        )
    points = {
        key: np.array([0.01, 0.02, 0.03]) for key in ("lift", "above_basket", "release", "withdraw")
    }
    scale = np.array([0.05] * 3)
    isolated = FixedReference(True, points, translation_scale=scale, rotation_scale=[0.5] * 3)
    points["lift"][:] = 100
    scale[:] = 100
    np.testing.assert_allclose(isolated.next_action([0] * 3, [0] * 3)[:3], [0.2, 0.4, 0.6])
