from __future__ import annotations

import math
import re
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
    """Validate a WorldEpisode-like record without importing the reference package."""
    issues: list[ValidationIssue] = []
    for field in ("episode_id", "schema"):
        if not isinstance(record.get(field), str) or not record[field]:
            issues.append(ValidationIssue("missing_field", f"{field} is required", field))
    if "revision_id" in record and not isinstance(record["revision_id"], str):
        issues.append(
            ValidationIssue("invalid_revision", "revision_id must be a string", "revision_id")
        )
    return issues


def validate_worldepisode_contract(record: dict[str, Any]) -> list[ValidationIssue]:
    """Validate the semantic fields required for strict WorldEpisode binding."""
    issues = validate_worldepisode_record(record)
    clocks = record.get("clock_graph", {}).get("clocks", [])
    clock_ids = {item.get("clock_id") for item in clocks if isinstance(item, dict)}
    if not clock_ids:
        issues.append(
            ValidationIssue("missing_clock_graph", "clock_graph requires a clock", "clock_graph")
        )
    for index, mapping in enumerate(record.get("clock_graph", {}).get("mappings", [])):
        if (
            not isinstance(mapping, dict)
            or "drift_model" not in mapping
            or "estimated_error" not in mapping
        ):
            issues.append(
                ValidationIssue(
                    "incomplete_clock_mapping",
                    "clock mapping requires drift_model and estimated_error",
                    f"clock_graph.mappings[{index}]",
                )
            )
    channels = record.get("action_space", {}).get("channels", [])
    for index, channel in enumerate(channels):
        if not isinstance(channel, dict):
            issues.append(
                ValidationIssue(
                    "invalid_action_channel",
                    "action channel must be a mapping",
                    f"action_space.channels[{index}]",
                )
            )
            continue
        required = {
            "control_mode",
            "parameterization",
            "reference_frame",
            "units",
            "semantics",
            "command_timestamp_semantics",
            "effective_timestamp_semantics",
        }
        missing = sorted(required - channel.keys())
        if missing:
            issues.append(
                ValidationIssue(
                    "incomplete_action_channel",
                    f"missing fields: {', '.join(missing)}",
                    f"action_space.channels[{index}]",
                )
            )
    world_revision = record.get("world_revision", {})
    world_revision_id = (
        world_revision.get("world_revision_id") if isinstance(world_revision, dict) else None
    )
    if not isinstance(world_revision_id, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", world_revision_id
    ):
        issues.append(
            ValidationIssue(
                "unbound_world_revision",
                "world_revision_id must be sha256:<digest>",
                "world_revision.world_revision_id",
            )
        )
    if "world_revision" not in record or "world_deltas" not in record:
        issues.append(
            ValidationIssue(
                "missing_world_trace",
                "world_revision and world_deltas are required",
                "world_deltas",
            )
        )
    if not isinstance(record.get("provenance"), dict) or not record["provenance"].get("source"):
        issues.append(
            ValidationIssue("missing_provenance", "provenance.source is required", "provenance")
        )
    if not isinstance(record.get("quality"), dict):
        issues.append(ValidationIssue("missing_quality", "quality record is required", "quality"))
    return issues
