from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..contracts import Observation


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    field: str | None = None


def validate_observation(observation: Observation) -> list[ValidationIssue]:
    """Validate the minimum observation semantics without requiring WorldEpisode."""
    issues: list[ValidationIssue] = []
    if observation.sequence < 0:
        issues.append(
            ValidationIssue("negative_sequence", "sequence must be non-negative", "sequence")
        )
    if not math.isfinite(observation.sim_time_s) or observation.sim_time_s < 0:
        issues.append(
            ValidationIssue(
                "invalid_sim_time", "sim_time_s must be finite and non-negative", "sim_time_s"
            )
        )
    timestamp = observation.source_timestamp
    if timestamp is not None and timestamp.value_ns < 0:
        issues.append(
            ValidationIssue(
                "invalid_timestamp", "source timestamp must be non-negative", "source_timestamp"
            )
        )
    if observation.received_monotonic_ns is not None and observation.received_monotonic_ns < 0:
        issues.append(
            ValidationIssue(
                "invalid_receive_time", "receive time must be non-negative", "received_monotonic_ns"
            )
        )
    return issues


def validate_worldepisode_record(record: dict[str, Any]) -> list[ValidationIssue]:
    """Validate a narrow adapter boundary for WorldEpisode-like records."""
    issues: list[ValidationIssue] = []
    for field in ("episode_id", "schema"):
        if not isinstance(record.get(field), str) or not record[field]:
            issues.append(ValidationIssue("missing_field", f"{field} is required", field))
    if "revision_id" in record and not isinstance(record["revision_id"], str):
        issues.append(
            ValidationIssue("invalid_revision", "revision_id must be a string", "revision_id")
        )
    return issues
