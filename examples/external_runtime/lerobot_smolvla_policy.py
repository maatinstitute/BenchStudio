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
  BENCHSTUDIO_LEROBOT_CHECKPOINT_SHA256: lowercase SHA-256 of the checkpoint
    manifest or other reviewed immutable checkpoint identity.
"""

from __future__ import annotations

import json
import os
import re
import sys
from contextlib import nullcontext
from typing import Any


def _error(message: str, *, code: str = "external_runtime_error") -> None:
    print(
        json.dumps(
            {"schema": "benchstudio.policy_error.v1", "code": code, "error": message}
        ),
        file=sys.stderr,
    )
    raise SystemExit(2)


checkpoint = os.environ.get("BENCHSTUDIO_LEROBOT_CHECKPOINT")
if not checkpoint:
    _error(
        "BENCHSTUDIO_LEROBOT_CHECKPOINT must name a local checkpoint directory",
        code="checkpoint_missing",
    )
if not os.path.isdir(checkpoint):
    _error(
        "BENCHSTUDIO_LEROBOT_CHECKPOINT does not name an existing directory",
        code="checkpoint_unavailable",
    )
checkpoint_sha256 = os.environ.get("BENCHSTUDIO_LEROBOT_CHECKPOINT_SHA256")
if (
    not isinstance(checkpoint_sha256, str)
    or re.fullmatch(r"[0-9a-f]{64}", checkpoint_sha256) is None
):
    _error(
        "BENCHSTUDIO_LEROBOT_CHECKPOINT_SHA256 must be lowercase SHA-256 hex",
        code="checkpoint_digest_invalid",
    )


try:
    import torch
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in the owning runtime
    _error(
        "LeRobot SmolVLA runtime is unavailable; install the external runtime "
        f"before starting this process ({exc.name})",
        code="runtime_unavailable",
    )


try:
    policy = SmolVLAPolicy.from_pretrained(checkpoint)
    policy.eval()
except Exception as exc:  # pragma: no cover - depends on external checkpoint/runtime
    _error(
        f"could not load SmolVLA checkpoint: {type(exc).__name__}: {exc}",
        code="checkpoint_load_failed",
    )



selected_device = os.environ.get("BENCHSTUDIO_LEROBOT_DEVICE")
if selected_device is not None:
    if re.fullmatch(r"(?:cpu|mps|cuda:[0-9]+)", selected_device) is None:
        _error("invalid explicit LeRobot device", code="device_invalid")
    if selected_device.startswith("cuda:"):
        index = int(selected_device.split(":")[1])
        if not torch.cuda.is_available() or index >= torch.cuda.device_count():
            _error("requested CUDA device is unavailable", code="device_unavailable")
    if selected_device == "mps" and not (
        hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    ):
        _error("requested MPS device is unavailable", code="device_unavailable")
    try:
        policy.to(torch.device(selected_device))
        model_device = next(policy.parameters()).device
        if model_device != torch.device(selected_device):
            raise RuntimeError("model parameters do not match requested device")
    except Exception as exc:
        _error(
            f"could not bind SmolVLA to requested device: {type(exc).__name__}: {exc}",
            code="device_binding_failed",
        )

def _tensorize(value: Any) -> Any:
    import numpy as np

    if isinstance(value, np.ndarray):
        return torch.from_numpy(value)
    if isinstance(value, dict):
        return {key: _tensorize(item) for key, item in value.items()}
    if isinstance(value, list):
        return torch.tensor(value)
    if isinstance(value, (int, float, bool)):
        return torch.tensor(value)
    raise ValueError("policy_batch values must be nested mappings, numeric arrays, or scalars")


def _to_device(value: Any, device: str) -> Any:
    if isinstance(value, dict):
        return {key: _to_device(item, device) for key, item in value.items()}
    if isinstance(value, torch.Tensor):
        return value.to(device)
    return value


def _predict(request: dict[str, Any]) -> dict[str, Any]:
    observation = request.get("observation")
    if not isinstance(observation, dict):
        raise ValueError("predict observation must be a mapping")
    payload = observation.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("policy_batch"), dict):
        raise ValueError("observation.payload.policy_batch is required")
    tensor_root = os.environ.get("BENCHSTUDIO_LOCAL_TENSOR_ROOT")
    if tensor_root:
        # Only the trusted local BenchStudio process may publish descriptors.
        from benchstudio.local_tensors import open_local_tensors

        input_context = open_local_tensors(payload["policy_batch"], root=tensor_root)
    else:
        input_context = nullcontext(payload["policy_batch"])
    with input_context as policy_batch:
        batch = _tensorize(policy_batch)
        if selected_device is not None:
            batch = _to_device(batch, selected_device)
        with torch.inference_mode():
            action = policy.select_action(batch)
        if not isinstance(action, torch.Tensor):
            raise ValueError("LeRobot policy returned a non-tensor action")
        values = action.detach().cpu().tolist()
        del batch
        del action
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
            "checkpoint_sha256": checkpoint_sha256,
            "device": selected_device or "checkpoint_default",
            "tensor_transport": "mmap" if tensor_root else "json",
        },
    }


for line in sys.stdin:
    try:
        request = json.loads(line)
        if (
            not isinstance(request, dict)
            or request.get("schema") != "benchstudio.policy_request.v1"
        ):
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
