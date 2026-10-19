"""Minimal persistent simulator process for the external-adapter example."""

from __future__ import annotations

import json
import sys

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
    print(
        json.dumps(
            {
                "observation": {
                    "sequence": step,
                    "sim_time_s": step * 0.05,
                    "payload": {"step": step},
                },
                "done": step >= 2,
                "success": step >= 2,
            }
        ),
        flush=True,
    )
