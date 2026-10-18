from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

ClockDomain = Literal["sim_time", "host_monotonic", "robot_clock"]


@dataclass(frozen=True)
class ModelCapabilityProfile:
    model_id: str
    family: Literal["vla", "planner", "world_model", "safety_monitor", "custom"]
    input_modalities: tuple[str, ...]
    output_representation: str
    supports_closed_loop: bool
    supports_action_chunks: bool
    supported_metrics: tuple[str, ...]

    def supports(self, metric: str) -> bool:
        return metric in self.supported_metrics


@dataclass(frozen=True)
class Timestamp:
    value_ns: int
    domain: ClockDomain
    uncertainty_ns: int | None = None


@dataclass(frozen=True)
class ObservationFrame:
    observation_id: str
    episode_id: str
    sequence: int
    source_timestamp: Timestamp | None
    received_monotonic_ns: int
    sensor_timestamp: Timestamp | None
    payload: dict[str, Any] = field(default_factory=dict)
    payload_digest: str | None = None


@dataclass(frozen=True)
class Observation:
    sequence: int
    sim_time_s: float
    payload: dict[str, Any] = field(default_factory=dict)
    source_timestamp: Timestamp | None = None
    received_monotonic_ns: int | None = None


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
