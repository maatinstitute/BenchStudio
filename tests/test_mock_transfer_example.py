from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_mock_transfer_checkpoint_runs_matched_campaigns(tmp_path):
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "examples/run_mock_transfer.py"), "--output", str(tmp_path)],
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["plan_compatibility"]["valid"] is True
    assert report["execution_and_scoring"] == "external"
    transfer = report["transfer_fidelity"]
    assert transfer["matched_pairs"] == 4
    assert transfer["complete_pairs"] == 4
    assert transfer["success_gap_physical_minus_simulation"] == -1.0
    assert report["summary"]["simulation"]["completed"] == 4
    assert report["summary"]["physical"]["completed"] == 4
