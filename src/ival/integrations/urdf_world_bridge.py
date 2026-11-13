"""Dependency-free URDF Studio world-bridge wire contracts.

This module extracts the serializable contract boundary from ``urdf-ops``.
The service, Pydantic models, HTTP transport, and robot authority remain
owned by URDF Studio; IVal can validate recorded wire evidence without
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


def parse_worldd_status_payload(
    payload: Mapping[str, Any], *, strict: bool = False
) -> WorldBridgeStatus:
    return WorldBridgeStatus(
        service=_string(payload.get("service"), "world-bridge", strict, "service"),
        runtime_mode=_string(payload.get("runtime_mode"), "in-process", strict, "runtime_mode"),
        active_sessions=_integer(payload.get("active_sessions"), 0, strict, "active_sessions"),
        max_events_per_session=_integer(
            payload.get("max_events_per_session"), 0, strict, "max_events_per_session"
        ),
        default_scenario_duration_ms=_integer(
            payload.get("default_scenario_duration_ms"), 0, strict, "default_scenario_duration_ms"
        ),
        transition_contract_version=_string(
            payload.get("transition_contract_version"),
            "",
            False,
            "transition_contract_version",
            allow_empty=True,
        )
        or None,
    )


def parse_worldd_ack_payload(
    payload: Mapping[str, Any], *, strict: bool = False
) -> WorldBridgeCommandAck:
    return WorldBridgeCommandAck(
        session_id=_string(payload.get("session_id"), "", strict, "session_id"),
        accepted=_boolean(payload.get("accepted"), False, strict, "accepted"),
        applied_joint_count=_integer(
            payload.get("applied_joint_count"), 0, strict, "applied_joint_count"
        ),
        scenario_time_ms=_integer(payload.get("scenario_time_ms"), 0, strict, "scenario_time_ms"),
        command_sequence=_integer(payload.get("command_sequence"), 0, strict, "command_sequence"),
    )


def parse_worldd_session_payload(
    payload: Mapping[str, Any], *, strict: bool = False
) -> WorldBridgeSessionSnapshot:
    event_values = payload.get("recent_events") or []
    transition_values = payload.get("recent_transitions") or []
    if not isinstance(event_values, list):
        if strict:
            raise ValueError("recent_events must be a list")
        event_values = []
    if not isinstance(transition_values, list):
        if strict:
            raise ValueError("recent_transitions must be a list")
        transition_values = []
    events = tuple(
        _parse_event(item, strict=strict) for item in event_values if isinstance(item, Mapping)
    )
    transitions = tuple(
        _parse_transition(item, strict=strict)
        for item in transition_values
        if isinstance(item, Mapping)
    )
    if strict and len(events) != len(event_values):
        raise ValueError("recent_events must contain only objects")
    if strict and len(transitions) != len(transition_values):
        raise ValueError("recent_transitions must contain only objects")
    return WorldBridgeSessionSnapshot(
        session_id=_string(payload.get("session_id"), "", strict, "session_id"),
        robot_name=_string(payload.get("robot_name"), "", strict, "robot_name"),
        urdf_sha256=payload.get("urdf_sha256"),
        camera_ids=tuple(_string_list(payload.get("camera_ids"), strict, "camera_ids")),
        created_at_ms=_timestamp_ms(payload.get("created_at_ns"), strict, "created_at_ns"),
        updated_at_ms=_timestamp_ms(payload.get("updated_at_ns"), strict, "updated_at_ns"),
        scenario_duration_ms=_integer(
            payload.get("scenario_duration_ms"), 0, strict, "scenario_duration_ms"
        ),
        scenario_time_ms=_integer(payload.get("scenario_time_ms"), 0, strict, "scenario_time_ms"),
        joint_state=_float_map(payload.get("joint_state_rad"), strict, "joint_state_rad"),
        last_command_sequence=_integer(
            payload.get("last_command_sequence"), 0, strict, "last_command_sequence"
        ),
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


def _parse_event(payload: Mapping[str, Any], *, strict: bool) -> WorldBridgeEvent:
    return WorldBridgeEvent(
        event_id=_string(payload.get("event_id"), "", strict, "event_id"),
        session_id=_string(payload.get("session_id"), "", strict, "session_id"),
        type=world_bridge_event_type_from_worldd(
            _string(payload.get("event_type"), "", strict, "event_type")
        ),
        timestamp_ms=_timestamp_ms(payload.get("timestamp_ns"), strict, "timestamp_ns"),
        payload=_mapping(payload.get("payload"), strict, "payload"),
    )


def _parse_transition(payload: Mapping[str, Any], *, strict: bool) -> WorldBridgeTransitionRecord:
    transition_type = _string(payload.get("transition_type"), "", strict, "transition_type")
    try:
        parsed_type = WorldBridgeTransitionType(transition_type)
    except ValueError as exc:
        raise ValueError(f"unsupported worldd transition type: {transition_type!r}") from exc
    mode = _string(
        payload.get("rollout_mode"), WorldBridgeRolloutMode.UNSPECIFIED.value, False, "rollout_mode"
    )
    try:
        parsed_mode = WorldBridgeRolloutMode(mode)
    except ValueError as exc:
        if strict:
            raise ValueError(f"unsupported rollout_mode: {mode!r}") from exc
        parsed_mode = WorldBridgeRolloutMode.UNSPECIFIED
    return WorldBridgeTransitionRecord(
        transition_id=_string(payload.get("transition_id"), "", strict, "transition_id"),
        session_id=_string(payload.get("session_id"), "", strict, "session_id"),
        type=parsed_type,
        timestamp_ms=_timestamp_ms(payload.get("timestamp_ns"), strict, "timestamp_ns"),
        source=_string(payload.get("source"), "worldd", False, "source"),
        sequence_id=(
            _integer(payload.get("sequence_id"), 0, strict, "sequence_id")
            if payload.get("sequence_id") is not None
            else None
        ),
        planner_id=payload.get("planner_id"),
        task_id=payload.get("task_id"),
        adapter_id=payload.get("adapter_id"),
        rollout_mode=parsed_mode,
        scenario_time_before_ms=_integer(
            payload.get("scenario_time_before_ms"), 0, strict, "scenario_time_before_ms"
        ),
        scenario_time_after_ms=_integer(
            payload.get("scenario_time_after_ms"), 0, strict, "scenario_time_after_ms"
        ),
        joint_state_before=_float_map(
            payload.get("joint_state_before_rad"), strict, "joint_state_before_rad"
        ),
        action_joint_positions=_float_map(
            payload.get("action_joint_positions_rad"), strict, "action_joint_positions_rad"
        ),
        joint_state_after=_float_map(
            payload.get("joint_state_after_rad"), strict, "joint_state_after_rad"
        ),
    )


def _string(
    value: Any, fallback: str, strict: bool, field_name: str, *, allow_empty: bool = False
) -> str:
    if isinstance(value, str):
        result = value
    elif value is None and not strict:
        result = fallback
    elif strict:
        raise ValueError(f"{field_name} must be a string")
    else:
        result = str(value)
    if not allow_empty and not result.strip():
        if strict:
            raise ValueError(f"{field_name} is required")
        return fallback
    return result


def _integer(value: Any, fallback: int, strict: bool, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if strict:
            raise ValueError(f"{field_name} must be an integer")
        return fallback
    if value < 0:
        if strict:
            raise ValueError(f"{field_name} must be non-negative")
        return fallback
    return value


def _boolean(value: Any, fallback: bool, strict: bool, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if not strict and isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if not strict and isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    if strict:
        raise ValueError(f"{field_name} must be a boolean")
    return fallback


def _timestamp_ms(value: Any, strict: bool, field_name: str) -> int:
    return _integer(value, 0, strict, field_name) // NANOSECONDS_PER_MILLISECOND


def _string_list(value: Any, strict: bool, field_name: str) -> list[str]:
    if not isinstance(value, list):
        if strict:
            raise ValueError(f"{field_name} must be a list")
        return []
    if strict and any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{field_name} must contain non-empty strings")
    return [item if isinstance(item, str) else str(item) for item in value]


def _mapping(value: Any, strict: bool, field_name: str) -> dict[str, Any]:
    if value is None and not strict:
        return {}
    if not isinstance(value, Mapping):
        if strict:
            raise ValueError(f"{field_name} must be an object")
        return {}
    return dict(value)


def _float_map(value: Any, strict: bool, field_name: str) -> dict[str, float]:
    raw = _mapping(value, strict, field_name)
    result: dict[str, float] = {}
    for name, item in raw.items():
        if not isinstance(name, str) or not name:
            if strict:
                raise ValueError(f"{field_name} keys must be non-empty strings")
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            if strict:
                raise ValueError(f"{field_name}.{name} must be numeric")
            continue
        parsed = float(item)
        if not math.isfinite(parsed):
            if strict:
                raise ValueError(f"{field_name}.{name} must be finite")
            continue
        result[name] = parsed
    return result
