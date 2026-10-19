from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_mock_workers_checkpoint_commits_every_attempt_once(tmp_path):
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "examples/run_mock_workers.py"), "--output", str(tmp_path)],
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["schema"] == "benchstudio.worker_checkpoint.v1"
    assert report["workers"] == 3
    assert report["planned"] == 8
    assert report["committed"] == 8
    assert report["failed"] == 0
    assert 0 < report["leased_out"] < report["planned"]
    assert report["missing"] == 0
    assert report["audit"] == {"attempts_complete": True, "evidence_verified": True}
