"""Minimal persistent policy process for the external-adapter example."""

from __future__ import annotations

import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    operation = request.get("operation")
    if operation == "close":
        print(json.dumps({"status": "closed"}), flush=True)
        break
    if operation == "reset":
        print(json.dumps({"status": "reset"}), flush=True)
        continue
    observation = request.get("observation", {})
    sequence = observation.get("sequence", 0)
    print(
        json.dumps(
            {
                "actions": [1],
                "metadata": {"runtime": "example", "observation_sequence": sequence},
            }
        ),
        flush=True,
    )
