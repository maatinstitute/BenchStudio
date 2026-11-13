from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Literal


@dataclass(frozen=True)
class InferenceEvent:
    episode_id: str
    step: int
    phase: Literal["warmup", "measured"]
    action_sha256: str
    observation_sha256: str
    latency_ms: float
    sampler_calls: int = 1
    chunk_calls: int = 1


@dataclass(frozen=True)
class InferenceScheduleAudit:
    valid: bool
    warmup_count: int
    measured_count: int
    issues: tuple[str, ...]


def audit_inference_schedule(
    events: Iterable[InferenceEvent],
    *,
    expected_measured_steps: Iterable[int],
    expected_episode_id: str | None = None,
) -> InferenceScheduleAudit:
    """Validate warmup/measured separation and frozen inference accounting."""
    rows = list(events)
    issues: list[str] = []
    expected_steps = list(expected_measured_steps)
    if not rows:
        return InferenceScheduleAudit(False, 0, 0, ("no inference events",))
    phases = [row.phase for row in rows]
    first_measured = phases.index("measured") if "measured" in phases else len(phases)
    if any(phase == "warmup" for phase in phases[first_measured:]):
        issues.append("warmup events must precede measured events")
    for index, row in enumerate(rows):
        if expected_episode_id is not None and row.episode_id != expected_episode_id:
            issues.append(f"event {index}: unexpected episode identity")
        if row.step < 0:
            issues.append(f"event {index}: step must be non-negative")
        if not row.action_sha256 or len(row.action_sha256) != 64:
            issues.append(f"event {index}: action digest is not a SHA-256 value")
        if not row.observation_sha256 or len(row.observation_sha256) != 64:
            issues.append(f"event {index}: observation digest is not a SHA-256 value")
        if not math.isfinite(row.latency_ms) or row.latency_ms < 0:
            issues.append(f"event {index}: latency must be finite and non-negative")
        if row.sampler_calls != row.chunk_calls:
            issues.append(f"event {index}: sampler/chunk counters disagree")
        if row.sampler_calls < 0 or row.chunk_calls < 0:
            issues.append(f"event {index}: inference counters must be non-negative")
    measured = [row for row in rows if row.phase == "measured"]
    actual_steps = [row.step for row in measured]
    if actual_steps != expected_steps:
        issues.append(
            f"measured step schedule differs: expected {expected_steps}, got {actual_steps}"
        )
    if len({(row.episode_id, row.phase, row.step) for row in rows}) != len(rows):
        issues.append("duplicate episode/phase/step inference event")
    return InferenceScheduleAudit(
        not issues,
        first_measured,
        len(measured),
        tuple(issues),
    )
