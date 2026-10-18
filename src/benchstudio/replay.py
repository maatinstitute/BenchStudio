from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .contracts import ActionChunk, Observation


class ReplayTraceError(ValueError):
    """Raised when a rollout trace cannot provide replayable joint actions."""


def load_joint_sequence(path: Path) -> list[dict[str, float]]:
    """Load the robot_joints stream used by URDF Studio rollout traces."""
    sequence: list[dict[str, float]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayTraceError(f"{path}:{line_number} is not valid JSON") from exc
        if record.get("stream") != "robot_joints":
            continue
        joints = record.get("state", {}).get("joint_positions")
        if isinstance(joints, dict) and joints:
            sequence.append({str(name): float(value) for name, value in joints.items()})
    if not sequence:
        raise ReplayTraceError(f"No robot_joints records found in trace: {path}")
    return sequence


class ReplayPolicy:
    """Policy adapter that replays a recorded joint-target sequence."""

    policy_id = "trace_replay"

    def __init__(self, joint_targets: list[dict[str, float]]) -> None:
        if not joint_targets:
            raise ReplayTraceError("Replay policy requires a non-empty joint sequence")
        self._joint_targets = joint_targets
        self._cursor = 0

    @classmethod
    def from_trace(cls, path: Path) -> "ReplayPolicy":
        return cls(load_joint_sequence(path))

    def reset(self, *, seed: int) -> None:
        del seed
        self._cursor = 0

    def predict(self, observation: Observation, *, denoising_steps: int | None) -> ActionChunk:
        del observation, denoising_steps
        index = min(self._cursor, len(self._joint_targets) - 1)
        self._cursor += 1
        return ActionChunk(actions=(self._joint_targets[index],))


class ReplaySimulator:
    """Minimal simulator facade for validating a recorded trace end-to-end."""

    simulator_id = "trace_replay_simulator"

    def __init__(self, *, steps: int, sim_step_s: float = 0.05) -> None:
        if steps < 1:
            raise ValueError("steps must be positive")
        self._steps = steps
        self._sim_step_s = sim_step_s

    def reset(self, *, seed: int) -> Observation:
        self._cursor = 0
        self._success = False
        return Observation(
            sequence=0,
            sim_time_s=0.0,
            payload={"seed": seed},
            received_monotonic_ns=time.monotonic_ns(),
        )

    def observe(self) -> Observation:
        return Observation(
            sequence=self._cursor,
            sim_time_s=self._cursor * self._sim_step_s,
            received_monotonic_ns=time.monotonic_ns(),
        )

    def step(self, action: Any) -> Observation:
        del action
        self._cursor += 1
        self._success = self._cursor >= self._steps
        return self.observe()

    def is_done(self) -> bool:
        return self._cursor >= self._steps

    def is_success(self) -> bool:
        return self._success

    def close(self) -> None:
        pass
