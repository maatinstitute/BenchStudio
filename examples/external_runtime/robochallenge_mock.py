"""Transport-only RoboChallenge mock client for protocol boundary tests.

It preserves opaque payload bytes and emits canonical JSON-safe records. It
does not simulate physics, execute actions, or score tasks.
"""

from __future__ import annotations

import hashlib
import json
import sys


def _required_string(request: dict[str, object], field: str) -> str:
    value = request.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _required_int(request: dict[str, object], field: str) -> int:
    value = request.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _payload(request: dict[str, object]) -> bytes:
    value = request.get("payload")
    if not isinstance(value, str):
        raise ValueError("payload must be a string")
    try:
        import base64

        return base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be valid base64") from exc


def _emit(record: dict[str, object]) -> None:
    print(json.dumps(record, sort_keys=True), flush=True)


for line in sys.stdin:
    if not line.strip():
        continue
    try:
        request = json.loads(line)
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        operation = request.get("operation")
        if operation == "close":
            _emit({"status": "closed", "execution_and_scoring": "external"})
            break
        payload = _payload(request)
        import base64

        encoded = base64.b64encode(payload).decode("ascii")
        digest = hashlib.sha256(payload).hexdigest()
        if operation == "observe":
            _emit(
                {
                    "event_type": "robochallenge_observation",
                    "observation_id": _required_string(request, "observation_id"),
                    "timestamp_ns": _required_int(request, "timestamp_ns"),
                    "payload_base64": encoded,
                    "payload_digest_sha256": digest,
                }
            )
        elif operation == "acknowledge":
            execution_timestamp = request.get("execution_timestamp_ns")
            if execution_timestamp is not None:
                if isinstance(execution_timestamp, bool) or not isinstance(execution_timestamp, int) or execution_timestamp < 0:
                    raise ValueError("execution_timestamp_ns must be a non-negative integer or null")
            _emit(
                {
                    "event_type": "robochallenge_action_acknowledged",
                    "action_id": _required_string(request, "action_id"),
                    "command_timestamp_ns": _required_int(request, "command_timestamp_ns"),
                    "execution_timestamp_ns": execution_timestamp,
                    "payload_base64": encoded,
                    "payload_digest_sha256": digest,
                }
            )
        else:
            raise ValueError("operation must be observe, acknowledge, or close")
    except (json.JSONDecodeError, ValueError) as exc:
        _emit({"status": "error", "error": str(exc), "execution_and_scoring": "external"})
