from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..contracts import ActionChunk, Observation, Policy
from ..integrations.policy_trace import TracePolicy


@dataclass(frozen=True)
class PolicyParityReport:
    checked_observations: int
    identical_actions: int
    mismatches: tuple[dict[str, object], ...]

    @property
    def equrevaent(self) -> bool:
        return not self.mismatches

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "reva_policy_parity_report_v1",
            "checked_observations": self.checked_observations,
            "identical_actions": self.identical_actions,
            "equrevaent": self.equrevaent,
            "mismatches": list(self.mismatches),
        }


@dataclass(frozen=True)
class ObservationParityReport:
    checked_observations: int
    identical_observations: int
    mismatches: tuple[dict[str, object], ...]
    duplicate_sequences: tuple[int, ...] = ()

    @property
    def equrevaent(self) -> bool:
        return not self.mismatches

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "reva_observation_parity_report_v1",
            "checked_observations": self.checked_observations,
            "identical_observations": self.identical_observations,
            "duplicate_sequences": list(self.duplicate_sequences),
            "equrevaent": self.equrevaent,
            "mismatches": list(self.mismatches),
        }


def write_parity_report(
    path: Path,
    *,
    policy: PolicyParityReport | None = None,
    observations: ObservationParityReport | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Write deterministic parity evidence without claiming model validity."""
    if policy is None and observations is None:
        raise ValueError("at least one parity report is required")
    payload: dict[str, object] = {
        "schema": "reva_parity_report_v1",
        "metadata": dict(metadata or {}),
    }
    if policy is not None:
        payload["policy"] = policy.to_dict()
    if observations is not None:
        payload["observations"] = observations.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def compare_policy_trace_files(reference_path: Path, instrumented_path: Path) -> PolicyParityReport:
    """Compare two frozen policy traces without importing either policy runtime.

    The comparison includes action payloads, action metadata, sequence coverage,
    and the observation digest binding carried by each trace row. It is evidence
    of trace equrevaence only; it does not establish model quality or task
    correctness.
    """
    reference = TracePolicy.from_jsonl(reference_path, policy_id="reference")
    instrumented = TracePolicy.from_jsonl(instrumented_path, policy_id="instrumented")
    expected = {row.sequence: row for row in reference.rows}
    actual = {row.sequence: row for row in instrumented.rows}
    mismatches: list[dict[str, object]] = []
    identical = 0
    for sequence in sorted(set(expected) | set(actual)):
        left = expected.get(sequence)
        right = actual.get(sequence)
        if left is None or right is None:
            mismatches.append(
                {
                    "sequence": sequence,
                    "kind": "missing_trace_row",
                    "reference_present": left is not None,
                    "instrumented_present": right is not None,
                }
            )
            continue
        left_action = _trace_action_digest(left.actions, left.metadata)
        right_action = _trace_action_digest(right.actions, right.metadata)
        if left_action == right_action and left.observation_sha256 == right.observation_sha256:
            identical += 1
            continue
        mismatches.append(
            {
                "sequence": sequence,
                "kind": "trace_row_mismatch",
                "reference_action_sha256": left_action,
                "instrumented_action_sha256": right_action,
                "reference_observation_sha256": left.observation_sha256,
                "instrumented_observation_sha256": right.observation_sha256,
            }
        )
    return PolicyParityReport(len(set(expected) | set(actual)), identical, tuple(mismatches))


def compare_observation_streams(
    reference: Iterable[Observation], instrumented: Iterable[Observation]
) -> ObservationParityReport:
    """Compare observation identity and payloads before output parity."""
    expected: dict[int, list[Observation]] = {}
    actual: dict[int, list[Observation]] = {}
    for observation in reference:
        expected.setdefault(observation.sequence, []).append(observation)
    for observation in instrumented:
        actual.setdefault(observation.sequence, []).append(observation)
    mismatches: list[dict[str, object]] = []
    identical = 0
    duplicates = tuple(
        sorted(
            sequence
            for sequence in set(expected) | set(actual)
            if len(expected.get(sequence, ())) > 1 or len(actual.get(sequence, ())) > 1
        )
    )
    checked = 0
    for sequence in sorted(set(expected) | set(actual)):
        left = expected.get(sequence, [])
        right = actual.get(sequence, [])
        checked += max(len(left), len(right))
        if sequence in duplicates:
            mismatches.append(
                {
                    "sequence": sequence,
                    "kind": "duplicate_sequence",
                    "expected_count": len(left),
                    "actual_count": len(right),
                }
            )
            continue
        left_digest = _observation_digest(left[0]) if left else None
        right_digest = _observation_digest(right[0]) if right else None
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
    return ObservationParityReport(checked, identical, tuple(mismatches), duplicates)


def _digest(action: ActionChunk) -> str:
    payload = {"actions": action.actions, "metadata": action.metadata}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _trace_action_digest(actions: tuple[object, ...], metadata: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            {"actions": actions, "metadata": metadata},
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode()
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
