"""Strict subprocess policy bridge for independently developed model runtimes."""

from __future__ import annotations

import json
import math
import os
import selectors
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
        _validate_command_options(policy_id, timeout_s, environment)
        self.command = tuple(command)
        self.policy_id = policy_id
        self.timeout_s = timeout_s
        self.cwd = cwd
        self.environment = dict(environment or {})
        self._seed: int | None = None

    def reset(self, *, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        self._seed = seed

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


class PersistentExternalCommandPolicy:
    """Keep an independent policy runtime alive across inference requests.

    The process receives one JSON request and returns one JSON response per line.
    Operations are ``reset``, ``predict`` and ``close``. This avoids measuring
    process startup as model inference and supports runtimes that keep a loaded
    checkpoint or accelerator context in memory.
    """

    policy_id = "persistent_external_command_policy"

    def __init__(
        self,
        command: Sequence[str],
        *,
        policy_id: str = "persistent_external_command_policy",
        timeout_s: float = 30.0,
        cwd: str | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("command must contain non-empty strings")
        _validate_command_options(policy_id, timeout_s, environment)
        self.command = tuple(command)
        self.policy_id = policy_id
        self.timeout_s = timeout_s
        self.cwd = cwd
        self.environment = dict(environment or {})
        self._process: subprocess.Popen[str] | None = None
        self._seed: int | None = None

    def reset(self, *, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        self._ensure_started()
        response = self._request(
            {
                "schema": "benchstudio.policy_request.v1",
                "operation": "reset",
                "seed": seed,
            }
        )
        _validate_policy_status(response)
        self._seed = seed

    def predict(self, observation: Observation, *, denoising_steps: int | None) -> ActionChunk:
        response = self._request(
            {
                "schema": "benchstudio.policy_request.v1",
                "operation": "predict",
                "seed": self._seed,
                "observation": _jsonable_observation(observation),
                "denoising_steps": denoising_steps,
            }
        )
        return _action_chunk(response)

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            self._request({"schema": "benchstudio.policy_request.v1", "operation": "close"})
        except (BrokenPipeError, TimeoutError, RuntimeError, ValueError):
            pass
        finally:
            self._terminate_process()

    def _ensure_started(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        environment = os.environ.copy()
        environment.update(self.environment)
        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.cwd,
            env=environment,
            bufsize=1,
        )

    def _request(self, request: dict[str, Any]) -> dict[str, Any]:
        self._ensure_started()
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise RuntimeError("persistent external policy process is unavailable")
        process.stdin.write(json.dumps(request, sort_keys=True) + "\n")
        process.stdin.flush()
        selector = selectors.DefaultSelector()
        try:
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(self.timeout_s):
                self._terminate_process()
                raise TimeoutError(f"external policy exceeded {self.timeout_s}s timeout")
            line = process.stdout.readline()
        finally:
            selector.close()
        if not line:
            detail = process.stderr.read().strip()[-1000:] if process.stderr else ""
            raise RuntimeError("external policy exited" + (f": {detail}" if detail else ""))
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("external policy returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise ValueError("external policy response must be a mapping")
        return response

    def _terminate_process(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


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


def _validate_command_options(
    identifier: str, timeout_s: float, environment: Mapping[str, str] | None
) -> None:
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("policy_id must be a non-empty string")
    if (
        isinstance(timeout_s, bool)
        or not isinstance(timeout_s, (int, float))
        or not math.isfinite(timeout_s)
        or timeout_s <= 0
    ):
        raise ValueError("timeout_s must be a finite positive number")
    if environment is not None and any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in environment.items()
    ):
        raise ValueError("environment keys and values must be strings")


def persistent_external_command_capabilities() -> ModelCapabilityProfile:
    capabilities = external_command_capabilities()
    return ModelCapabilityProfile(
        **{
            **capabilities.to_dict(),
            "model_id": "persistent_external_command_policy",
            "runtime_controls": tuple(capabilities.runtime_controls) + ("persistent_process",),
        }
    )


def external_vla_capabilities(model_id: str) -> ModelCapabilityProfile:
    """Describe a VLA protocol bridge without claiming ownership of its runtime.

    Named model adapters use the same strict JSON-line boundary as the generic
    persistent adapter.  Keeping the model identity in the capability record
    lets a frozen campaign distinguish SmolVLA/DM0.5-style evaluations while
    leaving checkpoint loading, preprocessing, and accelerator ownership in
    the external process.
    """
    if not model_id:
        raise ValueError("model_id must not be empty")
    return ModelCapabilityProfile(
        model_id=model_id,
        family="vla",
        input_modalities=("image", "language", "proprioception"),
        output_representation="action_chunk",
        supports_closed_loop=True,
        supports_action_chunks=True,
        supported_metrics=("success", "latency", "resource_use", "observation_age"),
        runtime_controls=("timeout_s", "command", "environment", "persistent_process"),
        timing_signals=("host_monotonic",),
        supports_variable_action_horizon=True,
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


def _validate_policy_status(response: dict[str, Any]) -> None:
    if response.get("status", "ok") not in {"ok", "reset", "closed"}:
        raise RuntimeError(f"external policy reset failed: {response.get('status')}")


def _action_chunk(response: dict[str, Any]) -> ActionChunk:
    actions = response.get("actions")
    if not isinstance(actions, list):
        raise ValueError("external policy response requires an actions array")
    metadata = response.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("external policy metadata must be a mapping")
    return ActionChunk(tuple(actions), dict(metadata))
