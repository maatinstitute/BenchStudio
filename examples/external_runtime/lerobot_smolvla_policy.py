#!/usr/bin/env python3
"""LeRobot-owned SmolVLA process for BenchStudio's JSON-line policy bridge.

This file intentionally lives outside the BenchStudio package. Run it from a
LeRobot environment with ``torch``, ``transformers``, and a local checkpoint.
The BenchStudio observation payload must contain a JSON-serializable
``policy_batch`` mapping whose values are numeric arrays accepted by the
checkpoint's LeRobot processor/configuration. Image tensors may be represented
as nested channel-first or channel-last arrays after the caller's preprocessing
has been frozen and documented.

Required environment variable:
  BENCHSTUDIO_LEROBOT_CHECKPOINT: local SmolVLA checkpoint directory.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def _error(message: str) -> None:
    print(json.dumps({"schema": "benchstudio.policy_error.v1", "error": message}), file=sys.stderr)
    raise SystemExit(2)


try:
    import torch
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in the owning runtime
    _error(
        "LeRobot SmolVLA runtime is unavailable; install the external runtime "
        f"before starting this process ({exc.name})"
    )


checkpoint = os.environ.get("BENCHSTUDIO_LEROBOT_CHECKPOINT")
if not checkpoint:
    _error("BENCHSTUDIO_LEROBOT_CHECKPOINT must name a local checkpoint directory")

try:
    policy = SmolVLAPolicy.from_pretrained(checkpoint)
    policy.eval()
except Exception as exc:  # pragma: no cover - depends on external checkpoint/runtime
    _error(f"could not load SmolVLA checkpoint: {type(exc).__name__}: {exc}")


def _tensorize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _tensorize(item) for key, item in value.items()}
    if isinstance(value, list):
        return torch.tensor(value)
    if isinstance(value, (int, float, bool)):
        return torch.tensor(value)
    raise ValueError("policy_batch values must be nested mappings, numeric arrays, or scalars")


def _predict(request: dict[str, Any]) -> dict[str, Any]:
    observation = request.get("observation")
    if not isinstance(observation, dict):
        raise ValueError("predict observation must be a mapping")
    payload = observation.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("policy_batch"), dict):
        raise ValueError("observation.payload.policy_batch is required")
    batch = _tensorize(payload["policy_batch"])
    with torch.inference_mode():
        action = policy.select_action(batch)
    if not isinstance(action, torch.Tensor):
        raise ValueError("LeRobot policy returned a non-tensor action")
    values = action.detach().cpu().tolist()
    # LeRobot normally returns [batch, action_dim]; BenchStudio consumes a
    # sequence of actions and applies its frozen action-prefix policy.
    if isinstance(values, list) and len(values) == 1 and isinstance(values[0], list):
        actions = [values[0]]
    elif isinstance(values, list) and values and isinstance(values[0], list):
        actions = values
    else:
        actions = [values]
    return {
        "actions": actions,
        "metadata": {
            "runtime": "lerobot",
            "policy": "smolvla",
            "observation_sequence": observation.get("sequence"),
            "checkpoint": checkpoint,
        },
    }


for line in sys.stdin:
    try:
        request = json.loads(line)
        if not isinstance(request, dict) or request.get("schema") != "benchstudio.policy_request.v1":
            raise ValueError("unsupported BenchStudio policy request schema")
        operation = request.get("operation")
        if operation == "reset":
            seed = request.get("seed")
            if type(seed) is not int:
                raise ValueError("reset seed must be an integer")
            torch.manual_seed(seed)
            policy.reset()
            response = {"status": "reset"}
        elif operation == "predict":
            response = _predict(request)
        elif operation == "close":
            print(json.dumps({"status": "closed"}), flush=True)
            break
        else:
            raise ValueError(f"unsupported policy operation: {operation}")
        print(json.dumps(response, sort_keys=True), flush=True)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema": "benchstudio.policy_error.v1",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            ),
            flush=True,
        )
