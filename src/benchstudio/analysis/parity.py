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
        expected = reference.predict(observation, denoising_steps=denoising_steps)
        actual = instrumented.predict(observation, denoising_steps=denoising_steps)
        expected_digest = _digest(expected)
        actual_digest = _digest(actual)
        checked += 1
        if expected_digest == actual_digest:
            identical += 1
        else:
            mismatches.append(
                {
                    "sequence": observation.sequence,
                    "expected_sha256": expected_digest,
                    "actual_sha256": actual_digest,
                }
            )
    return PolicyParityReport(checked, identical, tuple(mismatches))


def _digest(action: ActionChunk) -> str:
    payload = {"actions": action.actions, "metadata": action.metadata}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
