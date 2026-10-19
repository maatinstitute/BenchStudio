from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_mock_robustness_checkpoint_runs_and_preserves_pairing(tmp_path):
    root = Path(__file__).parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "examples/run_mock_robustness.py"),
            "--output",
            str(tmp_path / "run"),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["physics"] == "external"
    assert report["pairs"] == 2
    assert report["branches"] == 4
    results = [
        json.loads(line)
        for line in (tmp_path / "run" / "counterfactual-results.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [row["branch"] for row in results] == [
        "nominal",
        "intervention",
        "nominal",
        "intervention",
    ]
    assert all(row["metadata"]["physics"] is False for row in results)
