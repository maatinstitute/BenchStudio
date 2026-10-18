"""Fixed-duration geometric reference candidate; no competence claim.

Caller derives waypoints from source geometry and supplies a verified world-axis
rotation delta. This module does not infer rotation conventions from data.
"""

from __future__ import annotations

from typing import Any


def _vector(value: Any, shape: tuple[int, ...], name: str):
    import numpy as np

    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(f"invalid {name}")
    return result.copy()


class FixedReference:
    """The RoboPAD fixed-duration pick/place geometric reference."""

    PICK = (
        ("open", 5, "start", -1),
        ("approach", 20, "above_target", -1),
        ("descend", 20, "grasp", -1),
        ("close", 8, "grasp", 1),
    )
    PLACE = (
        ("lift", 20, "lift", 1),
        ("transport", 40, "above_basket", 1),
        ("lower", 20, "release", 1),
        ("release", 8, "release", -1),
        ("withdraw", 15, "withdraw", -1),
    )

    def __init__(
        self,
        source_held: bool,
        waypoints: dict[str, Any],
        *,
        translation_scale: Any,
        rotation_scale: Any,
    ) -> None:
        if type(source_held) is not bool:
            raise ValueError("source possession must be an explicit boolean")
        self.stages = tuple((() if source_held else self.PICK) + self.PLACE)
        required = {name for _stage, _duration, name, _gripper in self.stages}
        if not required <= set(waypoints):
            raise ValueError("missing source-derived waypoint")
        self.waypoints = {name: _vector(waypoints[name], (3,), name) for name in required}
        self.translation_scale = _vector(translation_scale, (3,), "translation scale")
        self.rotation_scale = _vector(rotation_scale, (3,), "rotation scale")
        import numpy as np

        if not np.allclose(self.translation_scale, 0.05, rtol=0, atol=1e-12) or not np.allclose(
            self.rotation_scale, 0.5, rtol=0, atol=1e-12
        ):
            raise ValueError("controller scales differ from pinned candidate design")
        self.actions = 0
        self.limit = sum(stage[1] for stage in self.stages)
        self.stage_index = 0
        self.stage_actions = 0

    @property
    def stage(self) -> str | None:
        return None if self.actions >= self.limit else self.stages[self.stage_index][0]

    def next_action(self, eef_position: Any, verified_world_rotation_delta: Any):
        """Return one clipped 7-DoF action and advance the fixed horizon."""
        import numpy as np

        if self.stage is None:
            raise StopIteration("fixed reference duration exhausted")
        position = _vector(eef_position, (3,), "eef position")
        rotation_delta = _vector(verified_world_rotation_delta, (3,), "rotation delta")
        _stage, duration, waypoint, gripper = self.stages[self.stage_index]
        action = np.concatenate(
            (
                (self.waypoints[waypoint] - position) / self.translation_scale,
                rotation_delta / self.rotation_scale,
                [gripper],
            )
        )
        action = np.clip(action, -1, 1)
        self.actions += 1
        self.stage_actions += 1
        if self.stage_actions == duration:
            self.stage_actions = 0
            self.stage_index += 1
        return action
