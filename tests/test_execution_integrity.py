from __future__ import annotations

import hashlib
import json

import pytest

from benchstudio.analysis import (
    compare_observation_streams,
    compare_policy_outputs,
    compare_policy_trace_files,
    write_parity_report,
)
from benchstudio.campaigns import WorkerLeaseManager
from benchstudio.contracts import Observation
from benchstudio.integrations import (
    POLICY_TRACE_SCHEMA,
    RoboChallengeAction,
    RoboChallengeObservation,
    RoboChallengeObserveOnlyAdapter,
    audit_robochallenge_wire_records,
    TracePolicy,
    observation_digest_sha256,
    preflight_worldepisode,
    run_replay_conformance,
    validate_robochallenge_message,
)
from benchstudio.integrations.policy_trace import PolicyTraceRow
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


@pytest.mark.parametrize("lease_seconds", [True, 0, float("nan"), float("inf")])
def test_worker_lease_rejects_invalid_duration(tmp_path, lease_seconds):
    with pytest.raises(ValueError, match="finite positive number"):
        WorkerLeaseManager(tmp_path / "leases", lease_seconds=lease_seconds)


def test_worker_lease_does_not_reclaim_malformed_persisted_lease(tmp_path):
    leases = WorkerLeaseManager(tmp_path / "leases", clock_ns=lambda: 100)
    path = tmp_path / "leases" / "attempt-1.lease"
    path.write_text(
        json.dumps(
            {
                "attempt_id": "attempt-1",
                "worker_id": "worker-a",
                "expires_at_ns": "0",
            }
        )
    )
    assert leases.acquire("attempt-1", "worker-b") is None


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


@pytest.mark.parametrize("seed", [True, 1.0, "1"])
def test_trace_policy_rejects_coerced_reset_seeds(seed):
    policy = TracePolicy((PolicyTraceRow(0, (0,), {}),))
    with pytest.raises(ValueError, match="seed must be an integer"):
        policy.reset(seed=seed)  # type: ignore[arg-type]


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


def test_trace_policy_verifies_expected_file_digest(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text(
        json.dumps({"schema": POLICY_TRACE_SCHEMA, "sequence": 0, "actions": [1]}) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    TracePolicy.from_jsonl(path, expected_sha256=digest)
    with pytest.raises(ValueError, match="trace digest mismatch"):
        TracePolicy.from_jsonl(path, expected_sha256="0" * 64)


def test_policy_trace_files_compare_action_and_observation_bindings(tmp_path):
    reference = tmp_path / "reference.jsonl"
    instrumented = tmp_path / "instrumented.jsonl"
    rows = [
        {"schema": POLICY_TRACE_SCHEMA, "sequence": 0, "actions": [1], "metadata": {"x": 1}},
        {"schema": POLICY_TRACE_SCHEMA, "sequence": 1, "actions": [2], "metadata": {"x": 1}},
    ]
    reference.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    instrumented.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    assert compare_policy_trace_files(reference, instrumented).equivalent
    changed = dict(rows[1], actions=[3])
    instrumented.write_text(
        json.dumps(rows[0]) + "\n" + json.dumps(changed) + "\n", encoding="utf-8"
    )
    report = compare_policy_trace_files(reference, instrumented)
    assert report.equivalent is False
    assert report.mismatches[0]["kind"] == "trace_row_mismatch"


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


def test_robochallenge_wire_records_round_trip_opaque_payloads():
    emitted: list[dict[str, object]] = []
    source = RoboChallengeObserveOnlyAdapter(emitted.append)
    observation_payload = b"wire-observation\x00"
    source.observe(
        RoboChallengeObservation(
            "obs-1", 10, observation_payload, hashlib.sha256(observation_payload).hexdigest()
        )
    )
    action_payload = b"wire-action\xff"
    source.action_acknowledged(
        RoboChallengeAction(
            "act-1", 11, action_payload, hashlib.sha256(action_payload).hexdigest()
        ),
        execution_timestamp_ns=12,
    )

    replayed: list[dict[str, object]] = []
    target = RoboChallengeObserveOnlyAdapter(replayed.append)
    for record in emitted:
        target.ingest_record(record)
    assert replayed == emitted
    assert target.audit().valid


@pytest.mark.parametrize(
    "record, message",
    [
        ({"event_type": "unknown"}, "unsupported event_type"),
        (
            {
                "event_type": "robochallenge_observation",
                "observation_id": "obs-1",
                "timestamp_ns": 1,
                "payload_base64": "not-base64!",
                "payload_digest_sha256": "0" * 64,
            },
            "payload_base64",
        ),
        (
            {
                "event_type": "robochallenge_action_acknowledged",
                "action_id": "act-1",
                "command_timestamp_ns": True,
                "payload_base64": "YQ==",
                "payload_digest_sha256": hashlib.sha256(b"a").hexdigest(),
                "execution_timestamp_ns": None,
            },
            "command_timestamp_ns",
        ),
    ],
)
def test_robochallenge_wire_ingestion_rejects_malformed_records(record, message):
    adapter = RoboChallengeObserveOnlyAdapter(lambda _: None)
    with pytest.raises(ValueError, match=message):
        adapter.ingest_record(record)
    assert adapter.audit().valid is False
    assert adapter.audit().event_count == 0


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


def test_robochallenge_adapter_audits_rejected_message_failures():
    records: list[dict[str, object]] = []
    adapter = RoboChallengeObserveOnlyAdapter(records.append)
    with pytest.raises(ValueError, match="payload digest"):
        adapter.observe(RoboChallengeObservation("bad-obs", 1, b"payload", "0" * 64))
    with pytest.raises(ValueError, match="execution timestamp"):
        adapter.action_acknowledged(
            RoboChallengeAction("bad-action", 2, b"action", hashlib.sha256(b"action").hexdigest()),
            execution_timestamp_ns=-1,
        )
    audit = adapter.audit()
    assert audit.valid is False
    assert audit.event_count == 0
    assert any("observation payload digest mismatch" in issue for issue in audit.issues)
    assert any("action execution timestamp must be non-negative" in issue for issue in audit.issues)


def test_robochallenge_wire_audit_retains_malformed_records_and_continues():
    payload = b"observation"
    report = audit_robochallenge_wire_records(
        [
            {"event_type": "unknown"},
            {
                "event_type": "robochallenge_observation",
                "observation_id": "obs-1",
                "timestamp_ns": 10,
                "payload_base64": "b2JzZXJ2YXRpb24=",
                "payload_digest_sha256": hashlib.sha256(payload).hexdigest(),
            },
        ]
    )
    assert report["valid"] is False
    assert report["event_count"] == 1
    assert report["observation_count"] == 1
    assert report["canonical_records"][0]["observation_id"] == "obs-1"
    assert any("unsupported event_type" in issue for issue in report["issues"])


def test_robochallenge_validation_rejects_malformed_runtime_types():
    malformed = RoboChallengeObservation(
        "",
        "10",
        "payload",
        "not-a-digest",  # type: ignore[arg-type]
    )
    issues = validate_robochallenge_message(malformed)
    assert "message identifier is required" in issues
    assert "message timestamp must be a non-negative integer" in issues
    assert "payload must be bytes" in issues
    assert "payload digest must be a string" not in issues

    records: list[dict[str, object]] = []
    adapter = RoboChallengeObserveOnlyAdapter(records.append)
    action = RoboChallengeAction("action-1", 1, b"action", hashlib.sha256(b"action").hexdigest())
    with pytest.raises(ValueError, match="execution timestamp must be a non-negative integer"):
        adapter.action_acknowledged(action, execution_timestamp_ns=True)  # type: ignore[arg-type]


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


def test_worldepisode_strict_fallback_reports_malformed_nested_contracts():
    result = preflight_worldepisode(
        {
            "episode_id": "episode-1",
            "schema": "worldepisode",
            "clock_graph": {
                "clocks": [{"clock_id": "sim"}],
                "mappings": [
                    {
                        "source_clock_id": "unknown",
                        "target_clock_id": "sim",
                        "drift_model": "linear",
                        "estimated_error": -1,
                    }
                ],
            },
            "action_space": {"channels": [{"control_mode": "position"}]},
            "world_revision": {"world_revision_id": "sha256:" + "a" * 64},
            "world_deltas": {},
            "provenance": {"source": "test"},
            "quality": {},
        },
        strict=True,
    )
    assert result.valid is False
    assert {item["code"] for item in result.diagnostics} >= {
        "unknown_clock_reference",
        "invalid_clock_uncertainty",
        "incomplete_action_channel",
        "invalid_world_trace",
    }

    malformed = preflight_worldepisode(
        {
            "episode_id": "episode-2",
            "schema": "worldepisode",
            "clock_graph": "not-a-mapping",
            "action_space": [],
            "world_deltas": [],
            "provenance": [],
            "quality": {},
        },
        strict=True,
    )
    assert malformed.valid is False
    assert {item["code"] for item in malformed.diagnostics} >= {
        "invalid_clock_graph",
        "invalid_action_space",
        "missing_provenance",
    }


def test_worldepisode_preflight_binds_frozen_identity_and_fails_closed_on_bad_payload():
    mismatch = preflight_worldepisode(
        {"episode_id": "episode-1", "schema": "worldepisode", "revision_id": "rev-1"},
        expected_episode_id="episode-2",
        expected_revision_id="rev-2",
    )
    assert mismatch.valid is False
    assert {item["code"] for item in mismatch.diagnostics} >= {
        "episode_identity_mismatch",
        "revision_identity_mismatch",
    }
    invalid = preflight_worldepisode([], expected_episode_id="episode-1")
    assert invalid.valid is False
    assert invalid.profile == "benchstudio_invalid_worldepisode_profile"


def test_worldepisode_preflight_accepts_canonical_nested_identity():
    result = preflight_worldepisode(
        {
            "schema": "worldepisode",
            "episode": {"episode_id": "episode-1"},
            "world_revision": {"world_revision_id": "rev-1"},
        },
        expected_episode_id="episode-1",
        expected_revision_id="rev-1",
    )
    assert result.valid is True
    assert result.diagnostics == ()


def test_replay_conformance_reports_no_physics_coverage():
    result = run_replay_conformance()
    assert result["passed"] is True
    assert result["physics_coverage"] == "none"
