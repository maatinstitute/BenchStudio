"""Dependency-lazy adapter for Genesis World scenes.

Genesis owns scene physics and robot safety. ReVa only binds the scene
to its observation/action/timing evidence contract through explicit callbacks;
it never guesses how a task-specific controller should consume an action.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from typing import Any

from ..contracts import Observation, Timestamp

ObservationFn = Callable[[Any], Any]
ActionFn = Callable[[Any, Any], None]
SuccessFn = Callable[[Any], bool]
SceneFn = Callable[[Any], None]


class GenesisSimulator:
    """Adapt a configured Genesis ``Scene`` to the ReVa contract."""

    simulator_id = "genesis_simulator"

    def __init__(
        self,
        scene: Any,
        *,
        observation_fn: ObservationFn,
        action_fn: ActionFn,
        success_fn: SuccessFn | None = None,
        reset_fn: SceneFn | None = None,
        step_fn: SceneFn | None = None,
        dt_s: float = 0.01,
        max_steps: int = 1000,
    ) -> None:
        if not callable(observation_fn):
            raise TypeError("observation_fn must be callable")
        if not callable(action_fn):
            raise TypeError("action_fn must be callable")
        if (
            isinstance(dt_s, bool)
            or not isinstance(dt_s, (int, float))
            or dt_s <= 0
            or not math.isfinite(dt_s)
        ):
            raise ValueError("dt_s must be finite and positive")
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
            raise ValueError("max_steps must be positive")
        if reset_fn is None and not callable(getattr(scene, "reset", None)):
            raise ValueError("scene.reset or reset_fn is required")
        if step_fn is None and not callable(getattr(scene, "step", None)):
            raise ValueError("scene.step or step_fn is required")
        self.scene = scene
        self.observation_fn = observation_fn
        self.action_fn = action_fn
        self.success_fn = success_fn
        self.reset_fn = reset_fn
        self.step_fn = step_fn
        self.dt_s = float(dt_s)
        self.max_steps = max_steps
        self._step = 0
        self._success = False

    def reset(self, *, seed: int) -> Observation:
        reset = self.reset_fn or getattr(self.scene, "reset")
        try:
            reset(seed=seed)
        except TypeError:
            reset()
        self._step = 0
        self._success = self._evaluate_success()
        return self.observe()

    def observe(self) -> Observation:
        payload = self.observation_fn(self.scene)
        if isinstance(payload, Mapping):
            normalized = dict(payload)
        else:
            normalized = {"state": payload}
        sim_time_s = self._step * self.dt_s
        return Observation(
            sequence=self._step,
            sim_time_s=sim_time_s,
            payload=normalized,
            source_timestamp=Timestamp(round(sim_time_s * 1_000_000_000), "sim_time"),
            received_monotonic_ns=time.monotonic_ns(),
        )

    def step(self, action: Any) -> Observation:
        self.action_fn(self.scene, action)
        (self.step_fn or getattr(self.scene, "step"))()
        self._step += 1
        self._success = self._evaluate_success()
        return self.observe()

    def is_done(self) -> bool:
        return self._step >= self.max_steps or self._success

    def is_success(self) -> bool:
        return self._success

    def close(self) -> None:
        closer = getattr(self.scene, "close", None) or getattr(self.scene, "destroy", None)
        if callable(closer):
            closer()

    def _evaluate_success(self) -> bool:
        return bool(self.success_fn(self.scene)) if self.success_fn is not None else False
