from __future__ import annotations

import json

from benchstudio.adapters import default_registry
from benchstudio.campaigns import CampaignExecutor, compile_campaign_spec
from benchstudio.integrations import observation_digest_sha256
from benchstudio.mock import MockSimulator
from benchstudio.model_adapters import default_model_registry


def test_frozen_trace_policy_campaign_preserves_observation_binding(tmp_path):
    simulator = MockSimulator()
    observations = [simulator.reset(seed=1)]
    for _ in range(4):
        observations.append(simulator.step(1))
    trace = tmp_path / "reference-trace.jsonl"
    trace.write_text(
        "".join(
            json.dumps(
                {
                    "schema": "benchstudio.policy_trace.v1",
                    "sequence": observation.sequence,
                    "actions": [1],
                    "metadata": {"schedule": "reference"},
                    "observation_sha256": observation_digest_sha256(observation),
                },
                sort_keys=True,
            )
            + "\n"
            for observation in observations
        ),
        encoding="utf-8",
    )
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "trace-parity-campaign"},
            "model": {
                "adapter": "trace",
                "adapter_config": {"path": str(trace)},
            },
            "task": {"task_id": "trace-task"},
            "environments": [{"id": "mock", "kind": "simulator", "adapter": "mock"}],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"action_prefix": 1, "max_episode_steps": 4}],
            },
        }
    )
    output = tmp_path / "campaign"
    result = CampaignExecutor(
        plan,
        output,
        adapter_registry=default_registry(discover_external=False),
        model_registry=default_model_registry(discover_external=False),
    ).run()
    assert result.committed_attempt_ids == ("attempt-000000",)
    summary = json.loads((output / "attempts" / "attempt-000000" / "summary.json").read_text())
    assert summary["success_count"] == 1
    assert summary["campaign_status"] == "completed"
