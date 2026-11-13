from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def test_robochallenge_mock_runs_observe_acknowledge_audit_loop():
    root = Path(__file__).parents[1]
    completed = subprocess.run(
        [sys.executable, str(root / "examples/run_robochallenge_mock.py")],
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["schema"] == "reva.robochallenge_mock_checkpoint.v1"
    assert report["valid"] is True
    assert report["observation_count"] == 1
    assert report["action_acknowledgment_count"] == 1
    assert report["event_count"] == 2
    assert report["execution_and_scoring"] == "external"
    assert report["payload_digests"] == {
        "observation": hashlib.sha256(b"mock-observation").hexdigest(),
        "action": hashlib.sha256(b"mock-action").hexdigest(),
    }
