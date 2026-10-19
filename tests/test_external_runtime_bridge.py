from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_lerobot_smolvla_bridge_fails_closed_without_checkpoint():
    root = Path(__file__).parents[1]
    environment = dict(os.environ)
    environment.pop("BENCHSTUDIO_LEROBOT_CHECKPOINT", None)
    result = subprocess.run(
        [sys.executable, str(root / "examples/external_runtime/lerobot_smolvla_policy.py")],
        input="",
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 2
    error = json.loads(result.stderr.splitlines()[0])
    assert error["schema"] == "benchstudio.policy_error.v1"
    assert error["code"] == "checkpoint_missing"
    assert "checkpoint" in error["error"].lower() or "runtime" in error["error"].lower()


def test_lerobot_smolvla_bridge_rejects_missing_checkpoint_directory(tmp_path):
    root = Path(__file__).parents[1]
    environment = dict(os.environ)
    environment["BENCHSTUDIO_LEROBOT_CHECKPOINT"] = str(tmp_path / "missing")
    environment["BENCHSTUDIO_LEROBOT_CHECKPOINT_SHA256"] = "a" * 64
    result = subprocess.run(
        [sys.executable, str(root / "examples/external_runtime/lerobot_smolvla_policy.py")],
        input="",
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 2
    error = json.loads(result.stderr.splitlines()[0])
    assert error["code"] == "checkpoint_unavailable"
