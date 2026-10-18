from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ActionSpec:
    """Meaning of an action vector at an adapter boundary."""

    name: str
    signal: Literal["joint_position", "joint_velocity", "ee_pose", "gripper", "custom"]
    units: str
    dimensions: int
    labels: tuple[str, ...] = field(default_factory=tuple)
    reference_frame: str | None = None
    ordering_id: str | None = None

    def __post_init__(self) -> None:
        if self.dimensions < 1:
            raise ValueError("dimensions must be positive")
        if self.labels and len(self.labels) != self.dimensions:
            raise ValueError("labels must match dimensions")


def validate_action(action: Any, spec: ActionSpec) -> list[str]:
    """Return deterministic validation errors instead of silently coercing semantics."""
    if not isinstance(action, (list, tuple)):
        return ["action must be a list or tuple"]
    if len(action) != spec.dimensions:
        return [f"expected {spec.dimensions} values, received {len(action)}"]
    errors = []
    for index, value in enumerate(action):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"action[{index}] is not numeric")
            continue
        if not math.isfinite(value):
            errors.append(f"action[{index}] is not finite")
    return errors
