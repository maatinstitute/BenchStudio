"""Strict action-trace policy adapter for deterministic parity experiments."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts import ActionChunk, Observation

POLICY_TRACE_SCHEMA = "ival.policy_trace.v1"


@dataclass(frozen=True)
class PolicyTraceRow:
    sequence: int
    actions: tuple[Any, ...]
    metadata: dict[str, Any]
    observation_sha256: str | None = None


class TracePolicy:
    """Replay frozen actions only for the expected observation sequence."""

    policy_id = "trace_policy"

    def __init__(self, rows: tuple[PolicyTraceRow, ...], *, policy_id: str = "trace_policy"):
        if not rows:
            raise ValueError("policy trace must contain at least one row")
        if not policy_id:
            raise ValueError("policy_id must not be empty")
        by_sequence = {row.sequence: row for row in rows}
        if len(by_sequence) != len(rows):
            raise ValueError("policy trace contains duplicate sequences")
        self.policy_id = policy_id
        self._rows = by_sequence
        self._reset_seed: int | None = None

    @classmethod
    def from_jsonl(
        cls,
        path: Path,
        *,
        policy_id: str = "trace_policy",
        expected_sha256: str | None = None,
    ) -> "TracePolicy":
        if expected_sha256 is not None:
            if len(expected_sha256) != 64 or any(
                char not in "0123456789abcdef" for char in expected_sha256
            ):
                raise ValueError("expected trace digest must be lowercase SHA-256 hex")
            actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_sha256 != expected_sha256:
                raise ValueError(
                    f"trace digest mismatch: expected {expected_sha256}, got {actual_sha256}"
                )
        rows: list[PolicyTraceRow] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"trace line {line_number} is not valid JSON") from exc
            if not isinstance(value, dict) or value.get("schema") != POLICY_TRACE_SCHEMA:
                raise ValueError(f"trace line {line_number} has an unsupported schema")
            sequence = value.get("sequence")
            actions = value.get("actions")
            metadata = value.get("metadata", {})
            observation_sha256 = value.get("observation_sha256")
            if type(sequence) is not int or sequence < 0:
                raise ValueError(f"trace line {line_number} sequence must be non-negative")
            if not isinstance(actions, list):
                raise ValueError(f"trace line {line_number} actions must be a list")
            if not isinstance(metadata, dict):
                raise ValueError(f"trace line {line_number} metadata must be a mapping")
            if observation_sha256 is not None and (
                not isinstance(observation_sha256, str)
                or len(observation_sha256) != 64
                or any(char not in "0123456789abcdef" for char in observation_sha256)
            ):
                raise ValueError(f"trace line {line_number} observation digest is invalid")
            rows.append(
                PolicyTraceRow(
                    sequence,
                    tuple(actions),
                    dict(metadata),
                    observation_sha256,
                )
            )
        return cls(tuple(rows), policy_id=policy_id)

    def reset(self, *, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        self._reset_seed = seed

    @property
    def rows(self) -> tuple[PolicyTraceRow, ...]:
        """Return trace rows in sequence order for independent parity checks."""
        return tuple(self._rows[sequence] for sequence in sorted(self._rows))

    def predict(self, observation: Observation, *, denoising_steps: int | None) -> ActionChunk:
        del denoising_steps
        try:
            row = self._rows[observation.sequence]
        except KeyError as exc:
            raise KeyError(
                f"trace has no action for observation sequence {observation.sequence}"
            ) from exc
        if row.observation_sha256 is not None:
            actual = observation_digest_sha256(observation)
            if actual != row.observation_sha256:
                raise ValueError(
                    f"observation digest mismatch for sequence {observation.sequence}: "
                    f"expected {row.observation_sha256}, got {actual}"
                )
        metadata = dict(row.metadata)
        if self._reset_seed is not None:
            metadata.setdefault("trace_seed", self._reset_seed)
        return ActionChunk(row.actions, metadata)


def observation_digest_sha256(observation: Observation) -> str:
    payload = {
        "sequence": observation.sequence,
        "sim_time_s": observation.sim_time_s,
        "payload": observation.payload,
        "source_timestamp": observation.source_timestamp,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
