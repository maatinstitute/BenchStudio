from __future__ import annotations

import json
import sys

from benchstudio.external_policy import PersistentExternalCommandPolicy
from benchstudio.external_simulator import ExternalCommandSimulator
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
