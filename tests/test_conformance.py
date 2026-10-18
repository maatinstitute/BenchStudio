from __future__ import annotations

from benchstudio.conformance import (
    ActionSpec,
    AdapterCapabilities,
    ScenarioContract,
    ScheduledAction,
    apply_zero_order_hold,
    audit_action_queue,
    validate_action,
    validate_action_timing,
    validate_adapter_capabilities,
    validate_observation,
    validate_scenario_pair,
)
from benchstudio.contracts import Observation, Timestamp


def test_action_validation_rejects_semantic_shape_and_nonfinite_values():
    spec = ActionSpec("arm", "joint_position", "rad", 2, labels=("j1", "j2"))
    assert validate_action([0.1], spec)
    assert validate_action([0.1, float("nan")], spec)
    assert validate_action([0.1, 0.2], spec) == []


def test_adapter_capabilities_require_consistent_timing_signals():
    issues = validate_adapter_capabilities(
        AdapterCapabilities(command_acknowledgment=True), require_execution_timestamps=True
    )
    assert "execution_timestamps are required by this evaluation profile" in issues
    assert validate_adapter_capabilities(AdapterCapabilities(command_acknowledgment=True)) == []


def test_scenario_pair_rejects_different_assets():
    base = ScenarioContract("task", "rev-1", "a", "init", "success-v1")
    other = ScenarioContract("task", "rev-1", "b", "init", "success-v1")
    assert validate_scenario_pair(base, other) == ["asset_digest_sha256 differs"]


def test_timestamped_observation_is_valid():
    observation = Observation(
        0, 0.0, source_timestamp=Timestamp(0, "sim_time"), received_monotonic_ns=1
    )
    assert validate_observation(observation) == []


def test_replay_timing_tracks_clock_domains_and_dropped_commands():
    dropped = ScheduledAction(
        "drop",
        10,
        20,
        [1],
        queue_sequence=2,
        dropped=True,
        drop_reason="controller_deadline",
    )
    effective = ScheduledAction("keep", 5, 10, [2], queue_sequence=1)
    audit = audit_action_queue([dropped, effective])
    assert audit.complete is True
    assert audit.effective == 1
    assert apply_zero_order_hold([dropped, effective], [20]) == [effective]


def test_replay_timing_rejects_mismatched_domains_and_deadline_miss():
    action = ScheduledAction(
        "late",
        20,
        30,
        [1],
        command_clock_domain="host_monotonic",
        effective_clock_domain="sim_time",
        deadline_ns=10,
    )
    issues = validate_action_timing(action)
    assert "command and effective timestamps use different clock domains" in issues
    assert "command_time_ns is after controller deadline" in issues


def test_replay_timing_respects_queue_sequence_for_equal_effective_times():
    first = ScheduledAction("z", 0, 10, [1], queue_sequence=1)
    second = ScheduledAction("a", 0, 10, [2], queue_sequence=2)
    assert apply_zero_order_hold([second, first], [10])[0].action == [2]


def test_replay_timing_rejects_mixed_queue_clock_domains():
    actions = [
        ScheduledAction("sim", 0, 1, [1]),
        ScheduledAction(
            "host",
            0,
            1,
            [2],
            command_clock_domain="host_monotonic",
            effective_clock_domain="host_monotonic",
        ),
    ]
    audit = audit_action_queue(actions)
    assert audit.complete is False
    assert "action queue mixes clock domains" in audit.issues


def test_replay_timing_rejects_malformed_runtime_types_without_raising():
    action = ScheduledAction(
        "bad",
        "10",  # type: ignore[arg-type]
        20,
        [1],
        command_clock_domain=["sim_time"],  # type: ignore[arg-type]
        queue_sequence=True,  # type: ignore[arg-type]
        deadline_ns="20",  # type: ignore[arg-type]
    )
    issues = validate_action_timing(action)
    assert "action timestamps must be non-negative integers" in issues
    assert any("clock domains must be one of" in issue for issue in issues)
    assert any("queue_sequence must be a non-negative integer" in issue for issue in issues)
    assert any("deadline_ns must be a non-negative integer" in issue for issue in issues)


def test_replay_timing_rejects_duplicate_ids_and_drop_metadata():
    actions = [
        ScheduledAction("same", 0, 1, [1], dropped="yes"),  # type: ignore[arg-type]
        ScheduledAction("same", 0, 1, [2], drop_reason="late"),
    ]
    audit = audit_action_queue(actions)
    assert audit.complete is False
    assert "action_id values must be unique" in audit.issues
    assert any("dropped must be boolean" in issue for issue in audit.issues)
    assert any("non-dropped actions cannot carry drop_reason" in issue for issue in audit.issues)
