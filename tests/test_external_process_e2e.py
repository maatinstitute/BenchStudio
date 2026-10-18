from __future__ import annotations

import json
import sys

from benchstudio.adapters import default_registry
from benchstudio.campaigns import CampaignExecutor, compile_campaign_spec
from benchstudio.external_policy import PersistentExternalCommandPolicy
from benchstudio.external_simulator import ExternalCommandSimulator
from benchstudio.model_adapters import default_model_registry
from benchstudio.runner import RunConfig, run_episodes


def test_persistent_external_policy_and_simulator_complete_closed_loop_run(tmp_path):
    policy_program = """import json, sys
for line in sys.stdin:
    request = json.loads(line)
    operation = request.get("operation")
    status = "closed" if operation == "close" else ("reset" if operation == "reset" else "ok")
    response = {"status": status, "actions": [1], "metadata": {"source": "policy"}}
    print(json.dumps(response), flush=True)
"""
    simulator_program = """import json, sys
step = 0
for line in sys.stdin:
    request = json.loads(line)
    operation = request.get("operation")
    if operation == "reset":
        step = 0
    elif operation == "step":
        step += 1
    elif operation == "close":
        break
    response = {
        "observation": {
            "sequence": step,
            "sim_time_s": step * 0.05,
            "payload": {"step": step},
        },
        "done": step >= 2,
        "success": step >= 2,
    }
    print(json.dumps(response), flush=True)
"""
    policy = PersistentExternalCommandPolicy([sys.executable, "-c", policy_program], timeout_s=5)
    simulator = ExternalCommandSimulator([sys.executable, "-c", simulator_program], timeout_s=5)
    summary = run_episodes(
        policy,
        simulator,
        RunConfig(episodes=1, action_prefix=1, max_episode_steps=3),
        tmp_path / "run",
    )
    assert summary["campaign_status"] == "completed"
    assert summary["success_count"] == 1
    assert summary["episodes"][0]["steps"] == 2
    events = [
        json.loads(line) for line in (tmp_path / "run" / "episodes.jsonl").read_text().splitlines()
    ]
    actions = [event for event in events if event.get("event_type") == "action_executed"]
    assert len(actions) == 2
    assert all(event["policy_latency_ms"] >= 0 for event in actions)


def test_registry_backed_campaign_runs_external_policy_and_simulator(tmp_path):
    policy_program = """import json, sys
for line in sys.stdin:
    request = json.loads(line)
    operation = request.get("operation")
    status = "closed" if operation == "close" else ("reset" if operation == "reset" else "ok")
    print(
        json.dumps({"status": status, "actions": [1], "metadata": {"source": "policy"}}),
        flush=True,
    )
"""
    simulator_program = """import json, sys
step = 0
for line in sys.stdin:
    request = json.loads(line)
    operation = request.get("operation")
    if operation == "reset":
        step = 0
    elif operation == "step":
        step += 1
    elif operation == "close":
        break
    print(json.dumps({
        "observation": {"sequence": step, "sim_time_s": step * 0.05, "payload": {"step": step}},
        "done": step >= 1,
        "success": step >= 1,
    }), flush=True)
"""
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "registry-external-process"},
            "model": {
                "adapter": "persistent_external_command",
                "adapter_config": {
                    "command": [sys.executable, "-c", policy_program],
                    "timeout_s": 5,
                },
            },
            "task": {"task_id": "external-task"},
            "environments": [
                {
                    "id": "external-simulator",
                    "kind": "simulator",
                    "adapter": "external_command",
                    "adapter_config": {
                        "command": [sys.executable, "-c", simulator_program],
                        "timeout_s": 5,
                    },
                }
            ],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"denoising_steps": 1, "action_prefix": 1, "max_episode_steps": 2}],
            },
        }
    )
    executor = CampaignExecutor(
        plan,
        tmp_path / "campaign",
        model_registry=default_model_registry(discover_external=False),
        adapter_registry=default_registry(discover_external=False),
    )
    result = executor.run()
    assert result.committed_attempt_ids == ("attempt-000000",)
    assert result.failed_attempt_ids == ()
    assert result.missing_attempt_ids == ()
    summary = json.loads(
        (tmp_path / "campaign" / "attempts" / "attempt-000000" / "summary.json").read_text()
    )
    assert summary["campaign_status"] == "completed"
    assert summary["success_count"] == 1
    assert executor.audit().attempts_complete is True
