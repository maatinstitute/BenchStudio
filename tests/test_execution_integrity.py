from __future__ import annotations

import hashlib
import json

import pytest

from benchstudio.analysis import (
    compare_observation_streams,
    compare_policy_outputs,
    write_parity_report,
)
from benchstudio.campaigns import WorkerLeaseManager
from benchstudio.contracts import Observation
from benchstudio.integrations import (
    POLICY_TRACE_SCHEMA,
    RoboChallengeAction,
    RoboChallengeObservation,
    RoboChallengeObserveOnlyAdapter,
    TracePolicy,
    observation_digest_sha256,
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


def test_parity_reports_are_serializable_evidence(tmp_path):
    policy_report = compare_policy_outputs(
        MockPolicy(), MockPolicy(), [Observation(0, 0.0)], seed=1, denoising_steps=2
    )
    path = tmp_path / "parity.json"
    write_parity_report(path, policy=policy_report, metadata={"checkpoint": "sha256:x"})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "benchstudio_parity_report_v1"
    assert payload["policy"]["equivalent"] is True


def test_policy_parity_records_instrumentation_failures():
    class FailingPolicy(MockPolicy):
        def predict(self, observation, *, denoising_steps):
            raise RuntimeError("instrumentation failure")

    report = compare_policy_outputs(
        MockPolicy(), FailingPolicy(), [Observation(0, 0.0)], seed=1, denoising_steps=2
    )
    assert report.equivalent is False
    assert report.mismatches[0]["actual_error"] == "RuntimeError: instrumentation failure"


def test_trace_policy_replays_actions_and_binds_observation_digest(tmp_path):
    observation = Observation(2, 0.2, payload={"joint": [1.0]})
    trace_path = tmp_path / "policy-trace.jsonl"
    trace_path.write_text(
        json.dumps(
            {
                "schema": POLICY_TRACE_SCHEMA,
                "sequence": 2,
                "actions": [0.5, -0.5],
                "metadata": {"source": "recorded"},
                "observation_sha256": observation_digest_sha256(observation),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    policy = TracePolicy.from_jsonl(trace_path)
    policy.reset(seed=9)
    result = policy.predict(observation, denoising_steps=2)
    assert result.actions == (0.5, -0.5)
    assert result.metadata == {"source": "recorded", "trace_seed": 9}
    with pytest.raises(ValueError, match="observation digest mismatch"):
        policy.predict(Observation(2, 0.2, payload={"joint": [2.0]}), denoising_steps=2)


def test_trace_policy_rejects_duplicate_sequences(tmp_path):
    path = tmp_path / "duplicate.jsonl"
    row = {"schema": POLICY_TRACE_SCHEMA, "sequence": 1, "actions": [1]}
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate sequences"):
        TracePolicy.from_jsonl(path)


def test_observation_parity_compares_payload_identity_and_missing_sequences():
    reference = [Observation(0, 0.0, payload={"camera": 1}), Observation(1, 0.1)]
    instrumented = [Observation(0, 0.0, payload={"camera": 2})]
    report = compare_observation_streams(reference, instrumented)
    assert report.checked_observations == 2
    assert report.identical_observations == 0
    assert {item["sequence"] for item in report.mismatches} == {0, 1}


def test_observation_parity_rejects_reused_sequence_ids():
    reference = [Observation(0, 0.0, payload={"camera": 1})]
    instrumented = [
        Observation(0, 0.0, payload={"camera": 1}),
        Observation(0, 0.0, payload={"camera": 1}),
    ]
    report = compare_observation_streams(reference, instrumented)
    assert report.equivalent is False
    assert report.duplicate_sequences == (0,)
    assert report.mismatches == (
        {"sequence": 0, "kind": "duplicate_sequence", "expected_count": 1, "actual_count": 2},
    )


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
    assert records[0]["payload_base64"] == "b2JzZXJ2YXRpb24tYnl0ZXM="
    assert records[1]["payload_base64"] == "YWN0aW9uLWJ5dGVz"
    audit = adapter.audit()
    assert audit.valid
    assert audit.observation_count == 1
    assert audit.action_acknowledgment_count == 1
    assert [record["adapter_sequence"] for record in records] == [0, 1]
    assert validate_robochallenge_message(RoboChallengeAction("bad", 1, b"x", "0" * 64)) == [
        "payload digest mismatch"
    ]
    with pytest.raises(ValueError, match="execution timestamp"):
        adapter.action_acknowledged(action, execution_timestamp_ns=-1)


def test_robochallenge_adapter_rejects_duplicate_and_reordered_messages():
    records: list[dict[str, object]] = []
    adapter = RoboChallengeObserveOnlyAdapter(records.append)
    payload = b"observation"
    first = RoboChallengeObservation("obs-1", 10, payload, hashlib.sha256(payload).hexdigest())
    adapter.observe(first)
    with pytest.raises(ValueError, match="duplicate observation_id"):
        adapter.observe(first)
    later = RoboChallengeObservation("obs-2", 9, payload, hashlib.sha256(payload).hexdigest())
    with pytest.raises(ValueError, match="non-decreasing"):
        adapter.observe(later)
    action_payload = b"action"
    action = RoboChallengeAction(
        "act-1", 11, action_payload, hashlib.sha256(action_payload).hexdigest()
    )
    adapter.action_acknowledged(action, execution_timestamp_ns=None)
    with pytest.raises(ValueError, match="duplicate action_id"):
        adapter.action_acknowledged(action, execution_timestamp_ns=None)
    assert adapter.audit().valid is False
    assert adapter.audit().event_count == 2


def test_worldepisode_binding_is_explicit_about_fallback_profile():
    result = preflight_worldepisode({"episode_id": "episode-1", "schema": "worldepisode"})
    assert result.valid
    assert result.profile in {
        "benchstudio_minimal_worldepisode_profile",
        "worldepisode_reference_validator",
    }


def test_worldepisode_strict_fallback_requires_semantic_contract():
    result = preflight_worldepisode(
        {"episode_id": "episode-1", "schema": "worldepisode"}, strict=True
    )
    assert result.valid is False
    assert result.profile == "benchstudio_strict_worldepisode_profile"
    assert {item["code"] for item in result.diagnostics} >= {
        "missing_clock_graph",
        "unbound_world_revision",
        "missing_world_trace",
    }


def test_replay_conformance_reports_no_physics_coverage():
    result = run_replay_conformance()
    assert result["passed"] is True
    assert result["physics_coverage"] == "none"
