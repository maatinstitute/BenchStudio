from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from ..contracts import ActionChunk, Observation, Policy


@dataclass(frozen=True)
class PolicyParityReport:
    checked_observations: int
    identical_actions: int
    mismatches: tuple[dict[str, object], ...]

    @property
    def equivalent(self) -> bool:
        return not self.mismatches


@dataclass(frozen=True)
class ObservationParityReport:
    checked_observations: int
    identical_observations: int
    mismatches: tuple[dict[str, object], ...]

    @property
    def equivalent(self) -> bool:
        return not self.mismatches


def compare_policy_outputs(
    reference: Policy,
    instrumented: Policy,
    observations: Iterable[Observation],
    *,
    seed: int,
    denoising_steps: int | None,
) -> PolicyParityReport:
    reference.reset(seed=seed)
    instrumented.reset(seed=seed)
    mismatches: list[dict[str, object]] = []
    checked = identical = 0
    for observation in observations:
        expected_error: Exception | None = None
        actual_error: Exception | None = None
        try:
            expected = reference.predict(observation, denoising_steps=denoising_steps)
        except Exception as exc:
            expected = None
            expected_error = exc
        try:
            actual = instrumented.predict(observation, denoising_steps=denoising_steps)
        except Exception as exc:
            actual = None
            actual_error = exc
        expected_digest = _digest(expected) if expected is not None else None
        actual_digest = _digest(actual) if actual is not None else None
        checked += 1
        if expected_digest == actual_digest and expected_error is None and actual_error is None:
            identical += 1
        else:
            mismatches.append(
                {
                    "sequence": observation.sequence,
                    "expected_sha256": expected_digest,
                    "actual_sha256": actual_digest,
                    "expected_error": _error(expected_error),
                    "actual_error": _error(actual_error),
                }
            )
    return PolicyParityReport(checked, identical, tuple(mismatches))


def compare_observation_streams(
    reference: Iterable[Observation], instrumented: Iterable[Observation]
) -> ObservationParityReport:
    """Compare observation identity and payloads before output parity."""
    expected = {observation.sequence: observation for observation in reference}
    actual = {observation.sequence: observation for observation in instrumented}
    mismatches: list[dict[str, object]] = []
    identical = 0
    for sequence in sorted(set(expected) | set(actual)):
        left = expected.get(sequence)
        right = actual.get(sequence)
        left_digest = _observation_digest(left) if left is not None else None
        right_digest = _observation_digest(right) if right is not None else None
        if left_digest == right_digest:
            identical += 1
        else:
            mismatches.append(
                {
                    "sequence": sequence,
                    "expected_sha256": left_digest,
                    "actual_sha256": right_digest,
                }
            )
    return ObservationParityReport(len(set(expected) | set(actual)), identical, tuple(mismatches))


def _digest(action: ActionChunk) -> str:
    payload = {"actions": action.actions, "metadata": action.metadata}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _observation_digest(observation: Observation) -> str:
    payload = {
        "sequence": observation.sequence,
        "sim_time_s": observation.sim_time_s,
        "payload": observation.payload,
        "source_timestamp": observation.source_timestamp,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _error(error: Exception | None) -> str | None:
    return f"{type(error).__name__}: {error}" if error is not None else None
