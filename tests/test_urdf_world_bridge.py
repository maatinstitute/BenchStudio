from __future__ import annotations

import math

import pytest

from ival.integrations import (
    WorldBridgeEventType,
    WorldBridgeRolloutMode,
    parse_worldd_ack_payload,
    parse_worldd_session_payload,
    parse_worldd_status_payload,
    validate_joint_command_payload,
    worldd_event_type_from_world_bridge,
)


def test_worldd_event_mapping_preserves_source_wire_names():
    assert worldd_event_type_from_world_bridge(WorldBridgeEventType.SESSION_CREATED) == (
        "session_created"
    )


def test_status_parser_preserves_strict_source_fields():
    status = parse_worldd_status_payload(
        {
            "service": "world-bridge",
            "runtime_mode": "in-process",
            "active_sessions": 2,
            "max_events_per_session": 100,
            "default_scenario_duration_ms": 5000,
            "transition_contract_version": "v1",
        },
        strict=True,
    )
    assert status.active_sessions == 2
    assert status.transition_contract_version == "v1"


def test_ack_parser_does_not_infer_execution_timestamp():
    ack = parse_worldd_ack_payload(
        {
            "session_id": "session-a",
            "accepted": True,
            "applied_joint_count": 2,
            "scenario_time_ms": 10,
            "command_sequence": 4,
        },
        strict=True,
    )
    assert ack.accepted is True
    assert ack.command_sequence == 4


def test_session_parser_converts_wire_timestamps_and_preserves_transition_mode():
    snapshot = parse_worldd_session_payload(
        {
            "session_id": "s",
            "robot_name": "ur5",
            "camera_ids": ["front"],
            "created_at_ns": 1_234_567,
            "updated_at_ns": 2_000_000,
            "scenario_duration_ms": 100,
            "scenario_time_ms": 10,
            "joint_state_rad": {"shoulder": 0.25},
            "last_command_sequence": 1,
            "recent_events": [
                {
                    "event_id": "e1",
                    "session_id": "s",
                    "event_type": "session_created",
                    "timestamp_ns": 1_000_000,
                    "payload": {},
                }
            ],
            "recent_transitions": [
                {
                    "transition_id": "t1",
                    "session_id": "s",
                    "transition_type": "transition.joint_command",
                    "timestamp_ns": 2_000_000,
                    "source": "ival",
                    "rollout_mode": "counterfactual",
                    "scenario_time_before_ms": 9,
                    "scenario_time_after_ms": 10,
                    "joint_state_before_rad": {"shoulder": 0.0},
                    "action_joint_positions_rad": {"shoulder": 0.25},
                    "joint_state_after_rad": {"shoulder": 0.25},
                }
            ],
        },
        strict=True,
    )
    assert snapshot.created_at_ms == 1
    assert snapshot.recent_events[0].type is WorldBridgeEventType.SESSION_CREATED
    assert snapshot.recent_transitions[0].rollout_mode is WorldBridgeRolloutMode.COUNTERFACTUAL


def test_joint_command_validation_rejects_nonfinite_and_coerced_values():
    assert validate_joint_command_payload({"joint_positions": {"j1": 0.1}}) == []
    assert validate_joint_command_payload({"joint_positions": {"j1": math.nan}})
    assert validate_joint_command_payload({"joint_positions": {"j1": True}})


@pytest.mark.parametrize(
    "payload",
    [
        {"session_id": "s", "accepted": "yes"},
        {"session_id": "s", "accepted": True, "command_sequence": -1},
    ],
)
def test_strict_ack_parser_rejects_invalid_wire_types(payload):
    with pytest.raises(ValueError):
        parse_worldd_ack_payload(payload, strict=True)
