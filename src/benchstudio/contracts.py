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
    input_contract: str = "observation.v1"
    inference_granularity: Literal[
        "single_action", "action_chunk", "trajectory", "state_prediction", "risk_score"
    ] = "action_chunk"
    runtime_controls: tuple[str, ...] = ()
    memory_bytes: int | None = None
    timing_signals: tuple[str, ...] = ()
    supports_async: bool = False
    supports_streaming: bool = False
    supports_cached_predictions: bool = False
    supports_variable_action_horizon: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible frozen capability record for evidence."""
        return {
            "model_id": self.model_id,
            "family": self.family,
            "input_modalities": list(self.input_modalities),
            "output_representation": self.output_representation,
            "supports_closed_loop": self.supports_closed_loop,
            "supports_action_chunks": self.supports_action_chunks,
            "supported_metrics": list(self.supported_metrics),
            "input_contract": self.input_contract,
            "inference_granularity": self.inference_granularity,
            "runtime_controls": list(self.runtime_controls),
            "memory_bytes": self.memory_bytes,
            "timing_signals": list(self.timing_signals),
            "supports_async": self.supports_async,
            "supports_streaming": self.supports_streaming,
            "supports_cached_predictions": self.supports_cached_predictions,
            "supports_variable_action_horizon": self.supports_variable_action_horizon,
        }

    def supports(self, metric: str) -> bool:
        return metric in self.supported_metrics

    def validate(self) -> list[str]:
        """Return errors that should be checked before scheduling an evaluation."""
        issues: list[str] = []
        if not isinstance(self.family, str) or self.family not in {
            "vla",
            "planner",
            "world_model",
            "safety_monitor",
            "custom",
        }:
            issues.append(f"unsupported family: {self.family}")
        if not isinstance(self.inference_granularity, str) or self.inference_granularity not in {
            "single_action",
            "action_chunk",
            "trajectory",
            "state_prediction",
            "risk_score",
        }:
            issues.append(f"unsupported inference_granularity: {self.inference_granularity}")
        if not self.model_id:
            issues.append("model_id is required")
        if not self.input_contract:
            issues.append("input_contract is required")
        if not self.output_representation:
            issues.append("output_representation is required")
        for name in (
            "supports_closed_loop",
            "supports_action_chunks",
            "supports_async",
            "supports_streaming",
            "supports_cached_predictions",
            "supports_variable_action_horizon",
        ):
            if not isinstance(getattr(self, name), bool):
                issues.append(f"{name} must be boolean")
        for name in ("input_modalities", "supported_metrics", "runtime_controls", "timing_signals"):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or not all(
                isinstance(value, str) and bool(value) for value in values
            ):
                issues.append(f"{name} must be a sequence of non-empty strings")
        if not self.input_modalities:
            issues.append("input_modalities must not be empty")
        if not self.supported_metrics:
            issues.append("supported_metrics must not be empty")
        if not isinstance(self.input_contract, str) or not self.input_contract:
            issues.append("input_contract is required")
        if self.memory_bytes is not None:
            if isinstance(self.memory_bytes, bool) or not isinstance(self.memory_bytes, int):
                issues.append("memory_bytes must be an integer or null")
            elif self.memory_bytes < 0:
                issues.append("memory_bytes must be non-negative")
        valid_runtime_controls = isinstance(self.runtime_controls, (tuple, list)) and all(
            isinstance(value, str) and bool(value) for value in self.runtime_controls
        )
        valid_timing_signals = isinstance(self.timing_signals, (tuple, list)) and all(
            isinstance(value, str) and bool(value) for value in self.timing_signals
        )
        if valid_runtime_controls and len(set(self.runtime_controls)) != len(self.runtime_controls):
            issues.append("runtime_controls must be unique")
        if valid_timing_signals and len(set(self.timing_signals)) != len(self.timing_signals):
            issues.append("timing_signals must be unique")
        if not self.supports_action_chunks and self.inference_granularity == "action_chunk":
            issues.append("action_chunk granularity requires supports_action_chunks")
        return issues


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
