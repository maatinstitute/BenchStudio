from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Observation:
    sequence: int
    sim_time_s: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionChunk:
    actions: tuple[Any, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


class Policy(Protocol):
    policy_id: str

    def reset(self, *, seed: int) -> None: ...

    def predict(self, observation: Observation, *, denoising_steps: int | None) -> ActionChunk: ...


class Simulator(Protocol):
    simulator_id: str

    def reset(self, *, seed: int) -> Observation: ...

    def observe(self) -> Observation: ...

    def step(self, action: Any) -> Observation: ...

    def is_done(self) -> bool: ...

    def is_success(self) -> bool: ...

    def close(self) -> None: ...
