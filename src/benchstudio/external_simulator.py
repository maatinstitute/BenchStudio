"""Persistent JSON-line simulator bridge for independent runtimes."""

from __future__ import annotations

import json
import math
import os
import selectors
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import Observation, Timestamp


class ExternalCommandSimulator:
    """Drive a simulator process through a strict line-oriented protocol.

    The process receives one JSON object per line and must return one JSON
    response per line. Operations are ``reset``, ``observe``, ``step`` and
    ``close``. Responses contain an ``observation`` object and may update
    ``done`` and ``success``. The command is always executed without a shell.
    """

    simulator_id = "external_command_simulator"

    def __init__(
        self,
        command: Sequence[str],
        *,
        simulator_id: str = "external_command_simulator",
        timeout_s: float = 30.0,
        cwd: str | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("command must contain non-empty strings")
        if not isinstance(simulator_id, str) or not simulator_id:
            raise ValueError("simulator_id must be a non-empty string")
        if (
            isinstance(timeout_s, bool)
            or not isinstance(timeout_s, (int, float))
            or not math.isfinite(timeout_s)
            or timeout_s <= 0
        ):
            raise ValueError("timeout_s must be a finite positive number")
        if environment is not None and any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in environment.items()
        ):
            raise ValueError("environment keys and values must be strings")
        self.command = tuple(command)
        self.simulator_id = simulator_id
        self.timeout_s = timeout_s
        self.cwd = cwd
        self.environment = dict(environment or {})
        self._process: subprocess.Popen[str] | None = None
        self._done = False
        self._success = False

    def reset(self, *, seed: int) -> Observation:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        self._ensure_started()
        response = self._request(
            {"schema": "benchstudio.simulator_request.v1", "operation": "reset", "seed": seed}
        )
        self._done = False
        self._success = False
        self._update_state(response)
        return _observation(response)

    def observe(self) -> Observation:
        response = self._request(
            {"schema": "benchstudio.simulator_request.v1", "operation": "observe"}
        )
        self._update_state(response)
        return _observation(response)

    def step(self, action: Any) -> Observation:
        response = self._request(
            {"schema": "benchstudio.simulator_request.v1", "operation": "step", "action": action}
        )
        self._update_state(response)
        return _observation(response)

    def is_done(self) -> bool:
        return self._done

    def is_success(self) -> bool:
        return self._success

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            self._request({"schema": "benchstudio.simulator_request.v1", "operation": "close"})
        except (BrokenPipeError, TimeoutError, RuntimeError, ValueError):
            pass
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=self.timeout_s)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            self._process = None

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
            raise RuntimeError("external simulator process is unavailable")
        process.stdin.write(json.dumps(request, sort_keys=True) + "\n")
        process.stdin.flush()
        selector = selectors.DefaultSelector()
        try:
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(self.timeout_s):
                raise TimeoutError(f"external simulator exceeded {self.timeout_s}s timeout")
            line = process.stdout.readline()
        finally:
            selector.close()
        if not line:
            detail = process.stderr.read().strip()[-1000:] if process.stderr else ""
            raise RuntimeError("external simulator exited" + (f": {detail}" if detail else ""))
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("external simulator returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise ValueError("external simulator response must be a mapping")
        return response

    def _update_state(self, response: dict[str, Any]) -> None:
        if "done" in response and not isinstance(response["done"], bool):
            raise ValueError("external simulator done must be boolean")
        if "success" in response and not isinstance(response["success"], bool):
            raise ValueError("external simulator success must be boolean")
        self._done = response.get("done", self._done)
        self._success = response.get("success", self._success)


def _observation(response: dict[str, Any]) -> Observation:
    value = response.get("observation")
    if not isinstance(value, dict):
        raise ValueError("external simulator response requires an observation mapping")
    source = value.get("source_timestamp")
    timestamp = None
    if source is not None:
        if not isinstance(source, dict) or not isinstance(source.get("domain"), str):
            raise ValueError("observation source_timestamp is invalid")
        source_value = source.get("value_ns")
        uncertainty = source.get("uncertainty_ns")
        if (
            isinstance(source_value, bool)
            or not isinstance(source_value, int)
            or source_value < 0
            or (
                uncertainty is not None
                and (
                    isinstance(uncertainty, bool)
                    or not isinstance(uncertainty, int)
                    or uncertainty < 0
                )
            )
        ):
            raise ValueError("observation source_timestamp values are invalid")
        timestamp = Timestamp(source_value, source["domain"], uncertainty)
    sequence = value.get("sequence")
    sim_time_s = value.get("sim_time_s")
    received_monotonic_ns = value.get("received_monotonic_ns")
    payload = value.get("payload", {})
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError("observation sequence must be a non-negative integer")
    if (
        isinstance(sim_time_s, bool)
        or not isinstance(sim_time_s, (int, float))
        or not math.isfinite(sim_time_s)
    ):
        raise ValueError("observation sim_time_s must be a finite number")
    if received_monotonic_ns is not None and (
        isinstance(received_monotonic_ns, bool)
        or not isinstance(received_monotonic_ns, int)
        or received_monotonic_ns < 0
    ):
        raise ValueError("observation received_monotonic_ns must be a non-negative integer")
    if not isinstance(payload, dict):
        raise ValueError("observation payload must be a mapping")
    return Observation(
        sequence=sequence,
        sim_time_s=float(sim_time_s),
        payload=dict(payload),
        source_timestamp=timestamp,
        received_monotonic_ns=received_monotonic_ns,
    )
