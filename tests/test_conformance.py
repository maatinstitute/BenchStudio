from __future__ import annotations

from benchstudio.conformance import (
    ActionSpec,
    AdapterCapabilities,
    ScenarioContract,
    validate_action,
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
    assert "command_acknowledgment requires execution_timestamps" in issues
    assert "execution_timestamps are required by this evaluation profile" in issues


def test_scenario_pair_rejects_different_assets():
    base = ScenarioContract("task", "rev-1", "a", "init", "success-v1")
    other = ScenarioContract("task", "rev-1", "b", "init", "success-v1")
    assert validate_scenario_pair(base, other) == ["asset_digest_sha256 differs"]


def test_timestamped_observation_is_valid():
    observation = Observation(
        0, 0.0, source_timestamp=Timestamp(0, "sim_time"), received_monotonic_ns=1
    )
    assert validate_observation(observation) == []
