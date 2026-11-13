"""Conservative straight-segment collision screen; not full robot safety.

The carried object is enclosed in a fixed world-axis box. Rotations during
motion, gripper/arm geometry, and tracking error require separate bounds.
This is the source-backed RoboPAD intervention preflight, not a safety proof.
"""

from __future__ import annotations

from typing import Any


def _vector(value: Any, shape: tuple[int, ...], name: str):
    import numpy as np

    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(f"invalid {name}")
    return result.copy()


def proper_rotation(value: Any):
    """Validate and return a finite proper 3-D rotation matrix."""
    import numpy as np

    result = np.asarray(value, dtype=float)
    if (
        result.shape != (3, 3)
        or not np.isfinite(result).all()
        or not np.allclose(result.T @ result, np.eye(3), atol=1e-8, rtol=0)
        or not np.isclose(np.linalg.det(result), 1, atol=1e-8, rtol=0)
    ):
        raise ValueError("proper rotation matrix required")
    return result


def swept_box_intersects(
    start: Any,
    end: Any,
    carried_world_half_extent: Any,
    obstacle_center: Any,
    obstacle_rotation: Any,
    obstacle_half_size: Any,
    *,
    margin: float,
) -> bool:
    """Return whether a swept carried box intersects an oriented obstacle.

    Touching counts as an intersection. The carried world-axis box is
    conservatively over-bounded in obstacle coordinates before the segment
    slab test, matching RoboPAD's reference implementation.
    """
    import numpy as np

    start = _vector(start, (3,), "segment start")
    end = _vector(end, (3,), "segment end")
    extent = _vector(carried_world_half_extent, (3,), "carried extent")
    center = _vector(obstacle_center, (3,), "obstacle center")
    half = _vector(obstacle_half_size, (3,), "obstacle size")
    orient = proper_rotation(obstacle_rotation)
    if (extent < 0).any() or (half <= 0).any() or not np.isfinite(margin) or margin < 0:
        raise ValueError("nonnegative carried extent/margin and positive obstacle size required")
    inflated = half + np.abs(orient.T) @ extent + margin
    a = orient.T @ (start - center)
    delta = orient.T @ (end - start)
    entry, leave = 0.0, 1.0
    for axis in range(3):
        if delta[axis] == 0:
            if a[axis] < -inflated[axis] or a[axis] > inflated[axis]:
                return False
            continue
        first = (-inflated[axis] - a[axis]) / delta[axis]
        second = (inflated[axis] - a[axis]) / delta[axis]
        entry = max(entry, min(first, second))
        leave = min(leave, max(first, second))
        if entry > leave:
            return False
    return True
