"""Persistent JSON-line simulator bridge for independent runtimes."""

from __future__ import annotations

import json
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
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if not simulator_id:
            raise ValueError("simulator_id must not be empty")
        self.command = tuple(command)
        self.simulator_id = simulator_id
        self.timeout_s = timeout_s
        self.cwd = cwd
        self.environment = dict(environment or {})
        self._process: subprocess.Popen[str] | None = None
        self._done = False
        self._success = False

    def reset(self, *, seed: int) -> Observation:
        self._ensure_started()
        response = self._request(
            {"schema": "benchstudio.simulator_request.v1", "operation": "reset", "seed": seed}
        )
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
        timestamp = Timestamp(
            int(source["value_ns"]), source["domain"], source.get("uncertainty_ns")
        )
    return Observation(
        sequence=int(value["sequence"]),
        sim_time_s=float(value["sim_time_s"]),
        payload=dict(value.get("payload", {})),
        source_timestamp=timestamp,
        received_monotonic_ns=value.get("received_monotonic_ns"),
    )
