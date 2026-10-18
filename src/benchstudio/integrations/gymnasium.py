"""Optional adapter for Gymnasium's reset/step environment protocol."""

from __future__ import annotations

import importlib
import time
from typing import Any, Callable, Mapping

from ..contracts import Observation, Timestamp

SuccessFn = Callable[[Any, float, bool, bool, Mapping[str, Any]], bool]


class GymnasiumSimulator:
    """Translate a Gymnasium environment into BenchStudio's simulator contract.

    The adapter preserves Gymnasium's terminated/truncated distinction in its
    internal lifecycle state and accepts either an explicit success callback or
    the conventional ``info['success']`` signal. It does not assign benchmark
    scoring authority to the wrapper.
    """

    simulator_id = "gymnasium_simulator"

    def __init__(
        self,
        env_id: str | None = None,
        *,
        env: Any | None = None,
        success_fn: SuccessFn | None = None,
        dt_s: float | None = None,
        **make_kwargs: Any,
    ) -> None:
        if env is None:
            if not env_id:
                raise ValueError("env_id is required when env is not supplied")
            try:
                gymnasium = importlib.import_module("gymnasium")
            except ModuleNotFoundError as exc:
                if exc.name == "gymnasium":
                    raise RuntimeError(
                        "Gymnasium backend requires the optional 'gymnasium' dependency"
                    ) from exc
                raise
            env = gymnasium.make(env_id, **make_kwargs)
        elif env_id is not None:
            raise ValueError("provide env_id or env, not both")
        if dt_s is not None and dt_s < 0:
            raise ValueError("dt_s must be non-negative")
        self.env = env
        self.success_fn = success_fn
        self.dt_s = dt_s
        self._step = 0
        self._sim_time_s = 0.0
        self._terminated = False
        self._truncated = False
        self._success = False
        self._latest: Observation | None = None
        self._last_info: dict[str, Any] = {}

    def reset(self, *, seed: int) -> Observation:
        result = self.env.reset(seed=seed)
        if isinstance(result, tuple) and len(result) == 2:
            observation, info = result
        else:
            observation, info = result, {}
        self._step = 0
        self._sim_time_s = 0.0
        self._terminated = False
        self._truncated = False
        self._last_info = dict(info) if isinstance(info, Mapping) else {}
        self._success = self._evaluate_success(observation, 0.0, False, False)
        self._latest = self._make_observation(observation)
        return self._latest

    def observe(self) -> Observation:
        if self._latest is None:
            raise RuntimeError("Gymnasium simulator must be reset before observation")
        return self._latest

    def step(self, action: Any) -> Observation:
        result = self.env.step(action)
        if not isinstance(result, tuple) or len(result) != 5:
            raise ValueError("Gymnasium environment step must return 5 values")
        observation, reward, terminated, truncated, info = result
        self._step += 1
        self._sim_time_s += self._dt_s()
        self._terminated = bool(terminated)
        self._truncated = bool(truncated)
        self._last_info = dict(info) if isinstance(info, Mapping) else {}
        self._success = self._evaluate_success(
            observation, float(reward), self._terminated, self._truncated
        )
        self._latest = self._make_observation(observation)
        return self._latest

    def is_done(self) -> bool:
        return self._terminated or self._truncated

    def is_success(self) -> bool:
        return self._success

    def close(self) -> None:
        self.env.close()

    def _dt_s(self) -> float:
        if self.dt_s is not None:
            return self.dt_s
        unwrapped = getattr(self.env, "unwrapped", self.env)
        return float(getattr(unwrapped, "dt", 1.0))

    def _make_observation(self, payload: Any) -> Observation:
        return Observation(
            sequence=self._step,
            sim_time_s=self._sim_time_s,
            payload={"observation": payload, "info": self._last_info},
            source_timestamp=Timestamp(round(self._sim_time_s * 1_000_000_000), "sim_time"),
            received_monotonic_ns=time.monotonic_ns(),
        )

    def _evaluate_success(
        self, observation: Any, reward: float, terminated: bool, truncated: bool
    ) -> bool:
        if self.success_fn is not None:
            return bool(
                self.success_fn(observation, reward, terminated, truncated, self._last_info)
            )
        return bool(self._last_info.get("success", False))
