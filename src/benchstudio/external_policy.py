"""Strict subprocess policy bridge for independently developed model runtimes."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import ActionChunk, ModelCapabilityProfile, Observation


class ExternalCommandPolicy:
    """Invoke a policy command with one JSON request per inference.

    The command is executed without a shell. Its stdout must be one JSON
    object containing an ``actions`` array and optional ``metadata`` mapping.
    This keeps model-runtime ownership outside BenchStudio while preserving a
    deterministic, auditable adapter boundary.
    """

    policy_id = "external_command_policy"

    def __init__(
        self,
        command: Sequence[str],
        *,
        policy_id: str = "external_command_policy",
        timeout_s: float = 30.0,
        cwd: str | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("command must contain non-empty strings")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if not policy_id:
            raise ValueError("policy_id must not be empty")
        self.command = tuple(command)
        self.policy_id = policy_id
        self.timeout_s = timeout_s
        self.cwd = cwd
        self.environment = dict(environment or {})
        self._seed: int | None = None

    def reset(self, *, seed: int) -> None:
        self._seed = int(seed)

    def predict(self, observation: Observation, *, denoising_steps: int | None) -> ActionChunk:
        request = {
            "schema": "benchstudio.policy_request.v1",
            "operation": "predict",
            "seed": self._seed,
            "observation": _jsonable_observation(observation),
            "denoising_steps": denoising_steps,
        }
        environment = os.environ.copy()
        environment.update(self.environment)
        try:
            completed = subprocess.run(
                self.command,
                input=json.dumps(request, sort_keys=True) + "\n",
                capture_output=True,
                text=True,
                check=False,
                cwd=self.cwd,
                env=environment,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"external policy exceeded {self.timeout_s}s timeout") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip()[-1000:]
            raise RuntimeError(
                f"external policy exited with code {completed.returncode}"
                + (f": {detail}" if detail else "")
            )
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("external policy returned invalid JSON") from exc
        if not isinstance(response, dict) or not isinstance(response.get("actions"), list):
            raise ValueError("external policy response requires an actions array")
        metadata = response.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("external policy metadata must be a mapping")
        return ActionChunk(tuple(response["actions"]), dict(metadata))


def external_command_capabilities() -> ModelCapabilityProfile:
    return ModelCapabilityProfile(
        model_id="external_command_policy",
        family="custom",
        input_modalities=("state", "image", "proprioception"),
        output_representation="action_chunk",
        supports_closed_loop=True,
        supports_action_chunks=True,
        supported_metrics=("success", "latency", "resource_use"),
        runtime_controls=("timeout_s", "command", "environment"),
        timing_signals=("host_monotonic",),
    )


def _jsonable_observation(observation: Observation) -> dict[str, Any]:
    source_timestamp = observation.source_timestamp
    return {
        "sequence": observation.sequence,
        "sim_time_s": observation.sim_time_s,
        "payload": observation.payload,
        "source_timestamp": (
            {
                "value_ns": source_timestamp.value_ns,
                "domain": source_timestamp.domain,
                "uncertainty_ns": source_timestamp.uncertainty_ns,
            }
            if source_timestamp is not None
            else None
        ),
        "received_monotonic_ns": observation.received_monotonic_ns,
    }
