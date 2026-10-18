from __future__ import annotations

import json

from benchstudio.mock import MockPolicy, MockSimulator
from benchstudio.runner import RunConfig, run_episodes


def test_run_emits_reproducible_artifact_set(tmp_path):
    summary = run_episodes(MockPolicy(), MockSimulator(), RunConfig(episodes=2), tmp_path / "run")
    assert summary["success_rate"] == 1.0
    assert (tmp_path / "run" / "manifest.json").exists()
    assert (tmp_path / "run" / "episodes.jsonl").exists()
    assert (tmp_path / "run" / "summary.json").exists()
    records = [
        json.loads(line) for line in (tmp_path / "run" / "episodes.jsonl").read_text().splitlines()
    ]
    assert records
    assert {"observation_age_ms", "policy_latency_ms", "action_prefix"} <= records[0].keys()


def test_action_prefix_changes_policy_call_count(tmp_path):
    one = run_episodes(
        MockPolicy(), MockSimulator(), RunConfig(episodes=1, action_prefix=1), tmp_path / "one"
    )
    two = run_episodes(
        MockPolicy(), MockSimulator(), RunConfig(episodes=1, action_prefix=2), tmp_path / "two"
    )
    assert one["episodes"][0]["policy_calls"] > two["episodes"][0]["policy_calls"]


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
    assert summary["success_rate"] == 1.0
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
