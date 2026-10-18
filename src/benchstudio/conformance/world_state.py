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
    clock_graph = record.get("clock_graph")
    if not isinstance(clock_graph, dict):
        issues.append(
            ValidationIssue("invalid_clock_graph", "clock_graph must be a mapping", "clock_graph")
        )
        clock_graph = {}
    clocks = clock_graph.get("clocks", [])
    if not isinstance(clocks, list):
        issues.append(
            ValidationIssue(
                "invalid_clocks", "clock_graph.clocks must be a list", "clock_graph.clocks"
            )
        )
        clocks = []
    clock_ids: set[str] = set()
    for index, clock in enumerate(clocks):
        if not isinstance(clock, dict) or not isinstance(clock.get("clock_id"), str):
            issues.append(
                ValidationIssue(
                    "invalid_clock",
                    "each clock requires a string clock_id",
                    f"clock_graph.clocks[{index}]",
                )
            )
            continue
        clock_id = clock["clock_id"]
        if not clock_id:
            issues.append(
                ValidationIssue(
                    "invalid_clock", "clock_id must not be empty", f"clock_graph.clocks[{index}]"
                )
            )
            continue
        if clock_id in clock_ids:
            issues.append(
                ValidationIssue(
                    "duplicate_clock", "clock_id must be unique", f"clock_graph.clocks[{index}]"
                )
            )
        clock_ids.add(clock_id)
    if not clock_ids:
        issues.append(
            ValidationIssue("missing_clock_graph", "clock_graph requires a clock", "clock_graph")
        )
    mappings = clock_graph.get("mappings", [])
    if not isinstance(mappings, list):
        issues.append(
            ValidationIssue(
                "invalid_clock_mappings",
                "clock_graph.mappings must be a list",
                "clock_graph.mappings",
            )
        )
        mappings = []
    for index, mapping in enumerate(mappings):
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
            continue
        for field in ("source_clock_id", "target_clock_id"):
            if field in mapping and mapping[field] not in clock_ids:
                issues.append(
                    ValidationIssue(
                        "unknown_clock_reference",
                        f"{field} must reference a declared clock",
                        f"clock_graph.mappings[{index}].{field}",
                    )
                )
        if not isinstance(mapping["drift_model"], str) or not mapping["drift_model"]:
            issues.append(
                ValidationIssue(
                    "invalid_drift_model",
                    "drift_model must be a non-empty string",
                    f"clock_graph.mappings[{index}].drift_model",
                )
            )
        estimated_error = mapping["estimated_error"]
        if (
            isinstance(estimated_error, bool)
            or not isinstance(estimated_error, (int, float))
            or not math.isfinite(estimated_error)
            or estimated_error < 0
        ):
            issues.append(
                ValidationIssue(
                    "invalid_clock_uncertainty",
                    "estimated_error must be a finite non-negative number",
                    f"clock_graph.mappings[{index}].estimated_error",
                )
            )
    action_space = record.get("action_space")
    if not isinstance(action_space, dict):
        issues.append(
            ValidationIssue(
                "invalid_action_space", "action_space must be a mapping", "action_space"
            )
        )
        action_space = {}
    channels = action_space.get("channels", [])
    if not isinstance(channels, list):
        issues.append(
            ValidationIssue(
                "invalid_action_channels",
                "action_space.channels must be a list",
                "action_space.channels",
            )
        )
        channels = []
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
        for field in required:
            if field in channel and not isinstance(channel[field], str):
                issues.append(
                    ValidationIssue(
                        "invalid_action_semantics",
                        f"{field} must be a string",
                        f"action_space.channels[{index}].{field}",
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
    elif not isinstance(record["world_deltas"], list):
        issues.append(
            ValidationIssue("invalid_world_trace", "world_deltas must be a list", "world_deltas")
        )
    provenance = record.get("provenance")
    if (
        not isinstance(provenance, dict)
        or not isinstance(provenance.get("source"), str)
        or not provenance.get("source")
    ):
        issues.append(
            ValidationIssue("missing_provenance", "provenance.source is required", "provenance")
        )
    if not isinstance(record.get("quality"), dict):
        issues.append(ValidationIssue("missing_quality", "quality record is required", "quality"))
    return issues
