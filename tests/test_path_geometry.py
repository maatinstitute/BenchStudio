import numpy as np
import pytest

from ival.conformance import proper_rotation, swept_box_intersects


def _check(start, end, extent=(0, 0, 0), orient=None, margin=0):
    return swept_box_intersects(
        start,
        end,
        extent,
        [0, 0, 0],
        np.eye(3) if orient is None else orient,
        [1, 1, 1],
        margin=margin,
    )


def test_crossing_and_clear_parallel_paths():
    assert _check([-2, 0, 0], [2, 0, 0])
    assert not _check([-2, 2, 0], [2, 2, 0])
    assert _check([-2, 1, 0], [2, 1, 0])


def test_carried_extent_and_margin_are_not_ignored():
    assert not _check([-2, 1.2, 0], [2, 1.2, 0])
    assert _check([-2, 1.2, 0], [2, 1.2, 0], extent=(0.3, 0.3, 0.3))
    assert _check([-2, 1.2, 0], [2, 1.2, 0], margin=0.3)


def test_stationary_and_reversed_segments():
    assert _check([0, 0, 0], [0, 0, 0])
    assert not _check([3, 0, 0], [3, 0, 0])
    assert _check([2, 0, 0], [-2, 0, 0])


def test_rotated_obstacle_coordinates():
    angle = np.pi / 4
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0],
            [np.sin(angle), np.cos(angle), 0],
            [0, 0, 1],
        ]
    )
    assert _check([-2, 1.3, 0], [2, 1.3, 0], orient=rotation)
    assert not _check([-2, 1.5, 0], [2, 1.5, 0], orient=rotation)


def test_invalid_extent_and_rotation_are_rejected():
    with pytest.raises(ValueError):
        _check([0] * 3, [1] * 3, extent=(-1, 0, 0))
    with pytest.raises(ValueError, match="proper rotation"):
        proper_rotation(np.eye(3) * 2)
