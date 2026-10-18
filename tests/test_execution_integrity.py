from __future__ import annotations

import hashlib

import pytest

from benchstudio.analysis import compare_policy_outputs
from benchstudio.campaigns import WorkerLeaseManager
from benchstudio.contracts import Observation
from benchstudio.integrations import (
    RoboChallengeAction,
    RoboChallengeObservation,
    RoboChallengeObserveOnlyAdapter,
    preflight_worldepisode,
    run_replay_conformance,
    validate_robochallenge_message,
)
from benchstudio.mock import MockPolicy


def test_worker_lease_is_exclusive_and_owner_bound(tmp_path):
    manager = WorkerLeaseManager(tmp_path / "leases", lease_seconds=10)
    lease = manager.acquire("attempt-1", "worker-a")
    assert lease is not None
    assert manager.acquire("attempt-1", "worker-b") is None
    with pytest.raises(ValueError, match="owner"):
        manager.release(type(lease)(lease.attempt_id, "worker-b", lease.expires_at_ns))
    manager.release(lease)
    assert manager.acquire("attempt-1", "worker-b") is not None


def test_policy_parity_detects_instrumentation_output_changes():
    observations = [Observation(0, 0.0), Observation(1, 0.1)]
    report = compare_policy_outputs(
        MockPolicy(), MockPolicy(), observations, seed=1, denoising_steps=2
    )
    assert report.equivalent
    assert report.identical_actions == 2


def test_robochallenge_adapter_preserves_opaque_payload_digests():
    records: list[dict[str, object]] = []
    adapter = RoboChallengeObserveOnlyAdapter(records.append)
    observation_payload = b"observation-bytes"
    observation = RoboChallengeObservation(
        "obs-1", 10, observation_payload, hashlib.sha256(observation_payload).hexdigest()
    )
    adapter.observe(observation)
    action_payload = b"action-bytes"
    action = RoboChallengeAction(
        "action-1", 11, action_payload, hashlib.sha256(action_payload).hexdigest()
    )
    adapter.action_acknowledged(action, execution_timestamp_ns=None)
    assert [record["event_type"] for record in records] == [
        "robochallenge_observation",
        "robochallenge_action_acknowledged",
    ]
    assert records[1]["execution_timestamp_status"] == "unavailable"
    assert validate_robochallenge_message(RoboChallengeAction("bad", 1, b"x", "0" * 64)) == [
        "payload digest mismatch"
    ]


def test_worldepisode_binding_is_explicit_about_fallback_profile():
    result = preflight_worldepisode({"episode_id": "episode-1", "schema": "worldepisode"})
    assert result.valid
    assert result.profile in {
        "benchstudio_minimal_worldepisode_profile",
        "worldepisode_reference_validator",
    }


def test_replay_conformance_reports_no_physics_coverage():
    result = run_replay_conformance()
    assert result["passed"] is True
    assert result["physics_coverage"] == "none"
