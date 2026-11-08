"""Dependency-free URDF Studio world-bridge wire contracts.

This module extracts the serializable contract boundary from ``urdf-ops``.
The service, Pydantic models, HTTP transport, and robot authority remain
owned by URDF Studio; BenchStudio can validate recorded wire evidence without
starting that runtime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

NANOSECONDS_PER_MILLISECOND = 1_000_000
WORLDD_SCHEMA_VERSION = "1"


class WorldBridgeEventType(str, Enum):
    SESSION_CREATED = "session.created"
    JOINT_COMMAND_APPLIED = "joint_command.applied"
    SCENARIO_TIME_UPDATED = "scenario_time.updated"


class WorldBridgeTransitionType(str, Enum):
    JOINT_COMMAND = "transition.joint_command"
    SCENARIO_TIME_UPDATE = "transition.scenario_time_update"


class WorldBridgeRolloutMode(str, Enum):
    UNSPECIFIED = "unspecified"
    LIVE = "live"
    COUNTERFACTUAL = "counterfactual"


@dataclass(frozen=True)
class WorldBridgeEvent:
    event_id: str
    session_id: str
    type: WorldBridgeEventType
    timestamp_ms: int
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldBridgeTransitionRecord:
    transition_id: str
    session_id: str
    type: WorldBridgeTransitionType
    timestamp_ms: int
    source: str
    sequence_id: int | None
    planner_id: str | None
    task_id: str | None
    adapter_id: str | None
    rollout_mode: WorldBridgeRolloutMode
    scenario_time_before_ms: int
    scenario_time_after_ms: int
    joint_state_before: dict[str, float]
    action_joint_positions: dict[str, float]
    joint_state_after: dict[str, float]


@dataclass(frozen=True)
class WorldBridgeSessionSnapshot:
    session_id: str
    robot_name: str
    urdf_sha256: str | None
    camera_ids: tuple[str, ...]
    created_at_ms: int
    updated_at_ms: int
    scenario_duration_ms: int
    scenario_time_ms: int
    joint_state: dict[str, float]
    last_command_sequence: int
    recent_events: tuple[WorldBridgeEvent, ...]
    recent_transitions: tuple[WorldBridgeTransitionRecord, ...]


@dataclass(frozen=True)
class WorldBridgeCommandAck:
    session_id: str
    accepted: bool
    applied_joint_count: int
    scenario_time_ms: int
    command_sequence: int


@dataclass(frozen=True)
class WorldBridgeStatus:
    service: str
    runtime_mode: str
    active_sessions: int
    max_events_per_session: int
    default_scenario_duration_ms: int
    transition_contract_version: str | None = None


_EVENT_TYPES = {
    "session_created": WorldBridgeEventType.SESSION_CREATED,
    "joint_command_applied": WorldBridgeEventType.JOINT_COMMAND_APPLIED,
    "scenario_time_updated": WorldBridgeEventType.SCENARIO_TIME_UPDATED,
}


def worldd_event_type_from_world_bridge(event_type: WorldBridgeEventType) -> str:
    """Map the URDF Studio event enum to its worldd wire spelling."""
    for wire, mapped in _EVENT_TYPES.items():
        if mapped is event_type:
            return wire
    raise ValueError(f"unsupported world-bridge event type: {event_type!r}")


def world_bridge_event_type_from_worldd(event_type: str) -> WorldBridgeEventType:
    try:
        return _EVENT_TYPES[event_type]
    except KeyError as exc:
        raise ValueError(f"unsupported worldd event type: {event_type!r}") from exc


def parse_worldd_status_payload(payload: Mapping[str, Any]) -> WorldBridgeStatus:
    return WorldBridgeStatus(
        service=_string(payload.get("service"), "service"),
        runtime_mode=_string(payload.get("runtime_mode"), "runtime_mode"),
        active_sessions=_integer(payload.get("active_sessions"), "active_sessions"),
        max_events_per_session=_integer(payload.get("max_events_per_session"), "max_events_per_session"),
        default_scenario_duration_ms=_integer(
            payload.get("default_scenario_duration_ms"), "default_scenario_duration_ms"
        ),
        transition_contract_version=_optional_string(
            payload.get("transition_contract_version"), "transition_contract_version"
        ),
    )


def parse_worldd_ack_payload(payload: Mapping[str, Any]) -> WorldBridgeCommandAck:
    return WorldBridgeCommandAck(
        session_id=_string(payload.get("session_id"), "session_id"),
        accepted=_boolean(payload.get("accepted"), "accepted"),
        applied_joint_count=_integer(payload.get("applied_joint_count"), "applied_joint_count"),
        scenario_time_ms=_integer(payload.get("scenario_time_ms"), "scenario_time_ms"),
        command_sequence=_integer(payload.get("command_sequence"), "command_sequence"),
    )


def parse_worldd_session_payload(payload: Mapping[str, Any]) -> WorldBridgeSessionSnapshot:
    event_values = _sequence(payload.get("recent_events"), "recent_events")
    transition_values = _sequence(payload.get("recent_transitions"), "recent_transitions")
    events = tuple(_parse_event(item) for item in event_values)
    transitions = tuple(_parse_transition(item) for item in transition_values)
    return WorldBridgeSessionSnapshot(
        session_id=_string(payload.get("session_id"), "session_id"),
        robot_name=_string(payload.get("robot_name"), "robot_name"),
        urdf_sha256=_optional_string(payload.get("urdf_sha256"), "urdf_sha256"),
        camera_ids=tuple(_string_list(payload.get("camera_ids"), "camera_ids")),
        created_at_ms=_timestamp_ms(payload.get("created_at_ns"), "created_at_ns"),
        updated_at_ms=_timestamp_ms(payload.get("updated_at_ns"), "updated_at_ns"),
        scenario_duration_ms=_integer(payload.get("scenario_duration_ms"), "scenario_duration_ms"),
        scenario_time_ms=_integer(payload.get("scenario_time_ms"), "scenario_time_ms"),
        joint_state=_float_map(payload.get("joint_state_rad"), "joint_state_rad"),
        last_command_sequence=_integer(payload.get("last_command_sequence"), "last_command_sequence"),
        recent_events=events,
        recent_transitions=transitions,
    )


def validate_joint_command_payload(payload: Mapping[str, Any]) -> list[str]:
    """Validate the source joint-command finite-value boundary."""
    values = payload.get("joint_positions")
    if not isinstance(values, Mapping):
        return ["joint_positions must be an object"]
    issues: list[str] = []
    for name, value in values.items():
        if not isinstance(name, str) or not name:
            issues.append("joint names must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            issues.append(f"joint_positions[{name!r}] must be numeric")
        elif not math.isfinite(float(value)):
            issues.append(f"joint_positions[{name!r}] must be finite")
    return issues


def _parse_event(payload: Mapping[str, Any]) -> WorldBridgeEvent:
    return WorldBridgeEvent(
        event_id=_string(payload.get("event_id"), "event_id"),
        session_id=_string(payload.get("session_id"), "session_id"),
        type=world_bridge_event_type_from_worldd(_string(payload.get("event_type"), "event_type")),
        timestamp_ms=_timestamp_ms(payload.get("timestamp_ns"), "timestamp_ns"),
        payload=_mapping(payload.get("payload"), "payload"),
    )


def _parse_transition(payload: Mapping[str, Any]) -> WorldBridgeTransitionRecord:
    transition_type = _string(payload.get("transition_type"), "transition_type")
    try:
        parsed_type = WorldBridgeTransitionType(transition_type)
    except ValueError as exc:
        raise ValueError(f"unsupported worldd transition type: {transition_type!r}") from exc
    mode = WorldBridgeRolloutMode(_string(payload.get("rollout_mode"), "rollout_mode"))
    return WorldBridgeTransitionRecord(
        transition_id=_string(payload.get("transition_id"), "transition_id"),
        session_id=_string(payload.get("session_id"), "session_id"),
        type=parsed_type,
        timestamp_ms=_timestamp_ms(payload.get("timestamp_ns"), "timestamp_ns"),
        source=_string(payload.get("source"), "source"),
        sequence_id=(
            _integer(payload.get("sequence_id"), "sequence_id")
            if payload.get("sequence_id") is not None else None
        ),
        planner_id=_optional_string(payload.get("planner_id"), "planner_id"),
        task_id=_optional_string(payload.get("task_id"), "task_id"),
        adapter_id=_optional_string(payload.get("adapter_id"), "adapter_id"),
        rollout_mode=mode,
        scenario_time_before_ms=_integer(
            payload.get("scenario_time_before_ms"), "scenario_time_before_ms"
        ),
        scenario_time_after_ms=_integer(
            payload.get("scenario_time_after_ms"), "scenario_time_after_ms"
        ),
        joint_state_before=_float_map(
            payload.get("joint_state_before_rad"), "joint_state_before_rad"
        ),
        action_joint_positions=_float_map(
            payload.get("action_joint_positions_rad"), "action_joint_positions_rad"
        ),
        joint_state_after=_float_map(
            payload.get("joint_state_after_rad"), "joint_state_after_rad"
        ),
    )


def _string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _timestamp_ms(value: Any, field_name: str) -> int:
    return _integer(value, field_name) // NANOSECONDS_PER_MILLISECOND


def _sequence(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{field_name} must be a list of objects")
    return value


def _string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{field_name} must be a list of non-empty strings")
    return value


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return dict(value)


def _float_map(value: Any, field_name: str) -> dict[str, float]:
    raw = _mapping(value, field_name)
    result: dict[str, float] = {}
    for name, item in raw.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{field_name}.{name} must be numeric")
        parsed = float(item)
        if not math.isfinite(parsed):
            raise ValueError(f"{field_name}.{name} must be finite")
        result[name] = parsed
    return result
