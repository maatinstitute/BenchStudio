from __future__ import annotations

import json

from benchstudio.analysis import ResourceBudget
from benchstudio.conformance import ActionSpec
from benchstudio.contracts import ActionChunk
from benchstudio.mock import MockPolicy, MockSimulator
from benchstudio.runner import RunConfig, run_episodes


def test_run_emits_reproducible_artifact_set(tmp_path):
    summary = run_episodes(MockPolicy(), MockSimulator(), RunConfig(episodes=2), tmp_path / "run")
    assert summary["scheduled_success_rate"] == 1.0
    assert (tmp_path / "run" / "manifest.json").exists()
    assert (tmp_path / "run" / "episodes.jsonl").exists()
    assert (tmp_path / "run" / "summary.json").exists()
    assert (tmp_path / "run" / "runtime-receipt.json").exists()
    records = [
        json.loads(line) for line in (tmp_path / "run" / "episodes.jsonl").read_text().splitlines()
    ]
    assert records
    assert {"observation_age_ms", "policy_latency_ms", "action_prefix"} <= records[0].keys()


def test_resource_sampler_is_recorded_as_attempt_evidence(tmp_path):
    samples = iter(
        [
            {"inference_calls": 10, "gpu_time_ms": 100.0, "gpu_memory_bytes": 512},
            {"inference_calls": 13, "gpu_time_ms": 125.0, "gpu_memory_bytes": 640},
        ]
    )
    run_dir = tmp_path / "resources"
    summary = run_episodes(
        MockPolicy(),
        MockSimulator(),
        RunConfig(episodes=1, action_prefix=1),
        run_dir,
        resource_sampler=lambda: next(samples),
    )
    assert summary["episodes"][0]["resource_metrics"] == {
        "gpu_memory_bytes": 640,
        "gpu_time_ms": 25.0,
        "inference_calls": 3,
    }
    events = [json.loads(line) for line in (run_dir / "episodes.jsonl").read_text().splitlines()]
    measurement = events[-1]
    assert measurement["event_type"] == "resource_measurement"
    assert measurement["delta"]["inference_calls"] == 3


def test_runtime_resource_budget_audit_is_written_to_summary(tmp_path):
    summary = run_episodes(
        MockPolicy(),
        MockSimulator(),
        RunConfig(
            episodes=1,
            action_prefix=1,
            resource_budget=ResourceBudget(max_inference_calls=1),
        ),
        tmp_path / "budget",
    )
    assert summary["resource_budget_audit"] == {
        "valid": False,
        "violations": ["inference_call_budget_exceeded"],
    }


def test_action_prefix_changes_policy_call_count(tmp_path):
    one = run_episodes(
        MockPolicy(), MockSimulator(), RunConfig(episodes=1, action_prefix=1), tmp_path / "one"
    )
    two = run_episodes(
        MockPolicy(), MockSimulator(), RunConfig(episodes=1, action_prefix=2), tmp_path / "two"
    )
    assert one["episodes"][0]["policy_calls"] > two["episodes"][0]["policy_calls"]


def test_runner_records_cached_execution_strategy(tmp_path):
    run_episodes(
        MockPolicy(),
        MockSimulator(),
        RunConfig(episodes=1, action_prefix=1, execution_strategy="cached"),
        tmp_path / "cached",
    )
    records = [
        json.loads(line)
        for line in (tmp_path / "cached" / "episodes.jsonl").read_text().splitlines()
    ]
    action_records = [record for record in records if record["event_type"] == "action_executed"]
    assert action_records
    assert action_records[0]["execution_strategy"] == "cached"


def test_observation_refresh_interval_creates_stale_observations(tmp_path):
    summary = run_episodes(
        MockPolicy(),
        MockSimulator(),
        RunConfig(episodes=1, action_prefix=1, observation_refresh_ticks=2),
        tmp_path / "stale",
    )
    records = [
        json.loads(line)
        for line in (tmp_path / "stale" / "episodes.jsonl").read_text().splitlines()
    ]
    assert summary["scheduled_success_rate"] == 1.0
    assert records[1]["observation_age_ms"] > records[0]["observation_age_ms"]


def test_actions_in_one_chunk_keep_the_same_source_observation(tmp_path):
    run_episodes(
        MockPolicy(),
        MockSimulator(),
        RunConfig(episodes=1, action_prefix=2, observation_refresh_ticks=1),
        tmp_path / "chunk",
    )
    records = [
        json.loads(line)
        for line in (tmp_path / "chunk" / "episodes.jsonl").read_text().splitlines()
    ]
    assert records[0]["inference_id"] == records[1]["inference_id"]
    assert records[0]["source_observation_sequence"] == records[1]["source_observation_sequence"]


def test_invalid_schedule_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="action_prefix"):
        RunConfig(action_prefix=0)


def test_runner_uses_action_contract_and_reports_invalid_policy_output(tmp_path):
    class BadPolicy(MockPolicy):
        def predict(self, observation, *, denoising_steps):
            return ActionChunk((1,))

    summary = run_episodes(
        BadPolicy(),
        MockSimulator(),
        RunConfig(
            episodes=1,
            action_prefix=1,
            action_spec=ActionSpec("arm", "joint_position", "rad", 2),
        ),
        tmp_path / "invalid-action",
    )
    assert summary["episodes"][0]["status"] == "policy_inference_error"
    assert "invalid_action" in summary["episodes"][0]["error"]


def test_policy_exception_is_recorded_as_episode_failure(tmp_path):
    class BrokenPolicy(MockPolicy):
        def predict(self, observation, *, denoising_steps):
            raise RuntimeError("inference offline")

    summary = run_episodes(
        BrokenPolicy(), MockSimulator(), RunConfig(episodes=1), tmp_path / "failure"
    )
    episode = summary["episodes"][0]
    assert summary["campaign_status"] == "failed"
    assert episode["status"] == "policy_inference_error"
    assert "inference offline" in episode["error"]
    assert summary["scheduled_success_rate"] == 0.0


def test_partial_trace_is_persisted_when_policy_crashes(tmp_path):
    class CrashAfterTwoCalls(MockPolicy):
        def __init__(self):
            self.calls = 0

        def predict(self, observation, *, denoising_steps):
            self.calls += 1
            if self.calls == 3:
                raise RuntimeError("simulated crash")
            return super().predict(observation, denoising_steps=denoising_steps)

    run_dir = tmp_path / "partial"
    summary = run_episodes(
        CrashAfterTwoCalls(), MockSimulator(), RunConfig(episodes=1, action_prefix=1), run_dir
    )
    records = [json.loads(line) for line in (run_dir / "episodes.jsonl").read_text().splitlines()]
    assert len(records) == 2
    assert summary["campaign_status"] == "failed"
    assert summary["episodes"][0]["status"] == "policy_inference_error"
    assert summary["completed_episode_count"] == 0


def test_invalid_simulator_observation_is_recorded_as_conformance_failure(tmp_path):
    class InvalidSimulator(MockSimulator):
        def reset(self, *, seed):
            observation = super().reset(seed=seed)
            from benchstudio.contracts import Observation

            return Observation(-1, float("nan"), payload=observation.payload)

    summary = run_episodes(MockPolicy(), InvalidSimulator(), RunConfig(), tmp_path / "invalid")
    assert summary["episodes"][0]["status"] == "simulator_reset_error"
    assert "invalid_sim_time" in summary["episodes"][0]["error"]
