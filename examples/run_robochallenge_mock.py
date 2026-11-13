#!/usr/bin/env python3
"""Run the RoboChallenge transport mock through the observe-only adapter."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from reva.integrations.robochallenge import audit_robochallenge_wire_records


def _request(process: subprocess.Popen[str], request: dict[str, Any]) -> dict[str, Any]:
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("mock transport pipes are unavailable")
    process.stdin.write(json.dumps(request, sort_keys=True) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise RuntimeError("mock transport exited without a response")
    response = json.loads(line)
    if not isinstance(response, dict):
        raise ValueError("mock transport response must be an object")
    if response.get("status") == "error":
        raise RuntimeError(str(response.get("error", "mock transport error")))
    return response


def main() -> int:
    client = Path(__file__).with_name("external_runtime") / "robochallenge_mock.py"
    process = subprocess.Popen(
        [sys.executable, str(client)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    records: list[dict[str, Any]] = []
    try:
        observation = b"mock-observation"
        action = b"mock-action"
        observation_b64 = base64.b64encode(observation).decode("ascii")
        action_b64 = base64.b64encode(action).decode("ascii")
        records.append(
            _request(
                process,
                {
                    "operation": "observe",
                    "observation_id": "obs-0001",
                    "timestamp_ns": 100,
                    "payload": observation_b64,
                },
            )
        )
        records.append(
            _request(
                process,
                {
                    "operation": "acknowledge",
                    "action_id": "act-0001",
                    "command_timestamp_ns": 110,
                    "execution_timestamp_ns": None,
                    "payload": action_b64,
                },
            )
        )
        _request(process, {"operation": "close"})
        report = audit_robochallenge_wire_records(records)
        report.update(
            {
                "schema": "reva.robochallenge_mock_checkpoint.v1",
                "transport": "mock_subprocess",
                "payload_digests": {
                    "observation": hashlib.sha256(observation).hexdigest(),
                    "action": hashlib.sha256(action).hexdigest(),
                },
            }
        )
        print(json.dumps(report, sort_keys=True))
        return 0 if report["valid"] else 2
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
