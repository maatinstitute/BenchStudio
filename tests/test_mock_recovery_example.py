from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_mock_recovery_checkpoint_resumes_without_duplicate_attempts(tmp_path):
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "examples/run_mock_recovery.py"), "--output", str(tmp_path)],
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["schema"] == "reva.recovery_checkpoint.v1"
    assert report["first_batch"] == {"committed": 2, "missing": 2}
    assert report["resumed_batch"] == {
        "committed": 2,
        "skipped_existing": 2,
        "missing": 0,
    }
    assert report["audit"]["attempts_complete"] is True
    assert report["audit"]["evidence_verified"] is True
