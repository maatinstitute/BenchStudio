"""Dependency-lazy adapter for Isaac Lab manager-based environments."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from typing import Any

from ..contracts import Observation, Timestamp

ObservationFn = Callable[[Any, Mapping[str, Any]], Any]
ActionFn = Callable[[Any], Any]
SuccessFn = Callable[[Any, Any, bool, bool, Mapping[str, Any]], bool]


class IsaacLabSimulator:
    """Adapt one vectorized Isaac Lab environment to REVA."""

    simulator_id = "isaaclab_simulator"

    def __init__(
        self,
        env: Any,
        *,
        observation_fn: ObservationFn | None = None,
        action_fn: ActionFn | None = None,
        success_fn: SuccessFn | None = None,
        env_index: int = 0,
        dt_s: float | None = None,
        max_steps: int = 1000,
    ) -> None:
        if not callable(getattr(env, "reset", None)) or not callable(getattr(env, "step", None)):
            raise TypeError("Isaac Lab env must provide reset and step")
        if isinstance(env_index, bool) or not isinstance(env_index, int) or env_index < 0:
            raise ValueError("env_index must be non-negative")
        if dt_s is not None and (
            isinstance(dt_s, bool)
            or not isinstance(dt_s, (int, float))
            or dt_s <= 0
            or not math.isfinite(dt_s)
        ):
            raise ValueError("dt_s must be finite and positive")
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.env = env
        self.observation_fn = observation_fn or _default_observation
        self.action_fn = action_fn or (lambda action: action)
        self.success_fn = success_fn
        self.env_index = env_index
        self.dt_s = float(dt_s) if dt_s is not None else _env_step_dt(env)
        self.max_steps = max_steps
        self._step = 0
        self._terminated = False
        self._truncated = False
        self._success = False
        self._observation: Observation | None = None

    def reset(self, *, seed: int) -> Observation:
        try:
            result = self.env.reset(seed=seed)
        except TypeError:
            result = self.env.reset()
        raw_observation, extras = _split_reset(result)
        self._step = 0
        self._terminated = False
        self._truncated = False
        self._success = self._evaluate_success(raw_observation, 0.0, extras)
        self._observation = self._make_observation(raw_observation, extras)
        return self._observation

    def observe(self) -> Observation:
        if self._observation is None:
            raise RuntimeError("Isaac Lab simulator must be reset before observation")
        return self._observation

    def step(self, action: Any) -> Observation:
        result = self.env.step(self.action_fn(action))
        if not isinstance(result, tuple) or len(result) not in {4, 5}:
            raise ValueError("Isaac Lab env.step must return 4 or 5 values")
        if len(result) == 4:
            raw_observation, reward, reset, extras = result
            terminated, truncated = bool(_select_env_value(reset, self.env_index)), False
        else:
            raw_observation, reward, terminated, truncated, extras = result
            terminated = bool(_select_env_value(terminated, self.env_index))
            truncated = bool(_select_env_value(truncated, self.env_index))
        extras = extras if isinstance(extras, Mapping) else {}
        self._step += 1
        self._terminated = terminated
        self._truncated = truncated
        self._success = self._evaluate_success(raw_observation, reward, extras)
        self._observation = self._make_observation(raw_observation, extras)
        return self._observation

    def is_done(self) -> bool:
        return self._step >= self.max_steps or self._terminated or self._truncated

    def is_success(self) -> bool:
        return self._success

    def close(self) -> None:
        closer = getattr(self.env, "close", None)
        if callable(closer):
            closer()

    def _make_observation(self, raw_observation: Any, extras: Mapping[str, Any]) -> Observation:
        payload = self.observation_fn(raw_observation, extras)
        normalized = dict(payload) if isinstance(payload, Mapping) else {"observation": payload}
        sim_time_s = self._step * self.dt_s
        return Observation(
            sequence=self._step,
            sim_time_s=sim_time_s,
            payload=normalized,
            source_timestamp=Timestamp(round(sim_time_s * 1_000_000_000), "sim_time"),
            received_monotonic_ns=time.monotonic_ns(),
        )

    def _evaluate_success(
        self, raw_observation: Any, reward: Any, extras: Mapping[str, Any]
    ) -> bool:
        if self.success_fn is not None:
            return bool(
                self.success_fn(
                    raw_observation,
                    reward,
                    self._terminated,
                    self._truncated,
                    extras,
                )
            )
        value = extras.get("success", extras.get("is_success", False))
        return bool(_select_env_value(value, self.env_index))


def _env_step_dt(env: Any) -> float:
    value = getattr(env, "step_dt", 1.0)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value <= 0
        or not math.isfinite(value)
    ):
        raise ValueError("Isaac Lab env.step_dt must be finite and positive")
    return float(value)


def _split_reset(result: Any) -> tuple[Any, Mapping[str, Any]]:
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], Mapping):
        return result[0], result[1]
    return result, {}


def _default_observation(raw_observation: Any, extras: Mapping[str, Any]) -> Any:
    del extras
    return raw_observation


def _select_env_value(value: Any, env_index: int) -> Any:
    if isinstance(value, (str, bytes, Mapping)):
        return value
    try:
        return value[env_index]
    except (IndexError, KeyError, TypeError):
        return value
