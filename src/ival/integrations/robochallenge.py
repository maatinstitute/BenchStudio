from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class RoboChallengeObservation:
    observation_id: str
    timestamp_ns: int
    payload: bytes
    payload_digest_sha256: str


@dataclass(frozen=True)
class RoboChallengeAction:
    action_id: str
    command_timestamp_ns: int
    payload: bytes
    payload_digest_sha256: str


@dataclass(frozen=True)
class RoboChallengeProtocolAudit:
    """Protocol-level accounting; it does not assert task success or safety."""

    observation_count: int
    action_acknowledgment_count: int
    event_count: int
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def validate_robochallenge_message(
    message: RoboChallengeObservation | RoboChallengeAction,
) -> list[str]:
    issues: list[str] = []
    if not isinstance(message, (RoboChallengeObservation, RoboChallengeAction)):
        return ["message must be a RoboChallenge observation or action"]
    identifier = (
        message.observation_id
        if isinstance(message, RoboChallengeObservation)
        else message.action_id
    )
    timestamp = (
        message.timestamp_ns
        if isinstance(message, RoboChallengeObservation)
        else message.command_timestamp_ns
    )
    if not isinstance(identifier, str) or not identifier:
        issues.append("message identifier is required")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        issues.append("message timestamp must be a non-negative integer")
    elif timestamp < 0:
        issues.append("message timestamp must be non-negative")
    if not isinstance(message.payload, bytes):
        issues.append("payload must be bytes")
    if not isinstance(message.payload_digest_sha256, str):
        issues.append("payload digest must be a string")
    elif (
        isinstance(message.payload, bytes)
        and hashlib.sha256(message.payload).hexdigest() != message.payload_digest_sha256
    ):
        issues.append("payload digest mismatch")
    return issues


class RoboChallengeObserveOnlyAdapter:
    """Record protocol messages while leaving execution and official scoring external.

    ``ingest_record`` accepts the canonical JSON-safe records emitted by this
    adapter, which makes a mock/client transport testable without interpreting
    the opaque RoboChallenge payload bytes.
    """

    def __init__(self, sink: Callable[[dict[str, object]], None]) -> None:
        if not callable(sink):
            raise TypeError("sink must be callable")
        self.sink = sink
        self._observation_ids: set[str] = set()
        self._action_ids: set[str] = set()
        self._last_observation_timestamp_ns: int | None = None
        self._issues: list[str] = []
        self._event_count = 0

    def ingest_record(self, record: Mapping[str, Any]) -> None:
        """Decode and validate one canonical JSON-safe protocol record."""
        if not isinstance(record, Mapping):
            self._reject_wire("record must be a mapping")
        event_type = record.get("event_type")
        if event_type == "robochallenge_observation":
            try:
                message = RoboChallengeObservation(
                    _wire_string(record, "observation_id"),
                    _wire_non_negative_int(record, "timestamp_ns"),
                    _wire_payload(record),
                    _wire_string(record, "payload_digest_sha256"),
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._reject_wire(f"invalid observation record: {exc}")
            self.observe(message)
            return
        if event_type == "robochallenge_action_acknowledged":
            execution_timestamp = record.get("execution_timestamp_ns")
            if execution_timestamp is not None:
                execution_timestamp = _wire_non_negative_int(record, "execution_timestamp_ns")
            try:
                message = RoboChallengeAction(
                    _wire_string(record, "action_id"),
                    _wire_non_negative_int(record, "command_timestamp_ns"),
                    _wire_payload(record),
                    _wire_string(record, "payload_digest_sha256"),
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._reject_wire(f"invalid action record: {exc}")
            self.action_acknowledged(message, execution_timestamp_ns=execution_timestamp)
            return
        self._reject_wire("unsupported event_type")

    def observe(self, message: RoboChallengeObservation) -> None:
        issues = validate_robochallenge_message(message)
        if issues:
            self._issues.extend(f"observation {issue}" for issue in issues)
            raise ValueError("invalid RoboChallenge observation: " + "; ".join(issues))
        if message.observation_id in self._observation_ids:
            issue = f"duplicate observation_id: {message.observation_id}"
            self._issues.append(issue)
            raise ValueError(issue)
        if (
            self._last_observation_timestamp_ns is not None
            and message.timestamp_ns < self._last_observation_timestamp_ns
        ):
            issue = "observation timestamps must be non-decreasing"
            self._issues.append(issue)
            raise ValueError(issue)
        self._observation_ids.add(message.observation_id)
        self._last_observation_timestamp_ns = message.timestamp_ns
        self._event_count += 1
        self.sink(
            {
                "event_type": "robochallenge_observation",
                "adapter_sequence": self._event_count - 1,
                "observation_id": message.observation_id,
                "timestamp_ns": message.timestamp_ns,
                "payload_base64": base64.b64encode(message.payload).decode("ascii"),
                "payload_digest_sha256": message.payload_digest_sha256,
            }
        )

    def action_acknowledged(
        self, message: RoboChallengeAction, *, execution_timestamp_ns: int | None
    ) -> None:
        issues = validate_robochallenge_message(message)
        if execution_timestamp_ns is not None and (
            not isinstance(execution_timestamp_ns, int) or isinstance(execution_timestamp_ns, bool)
        ):
            issues.append("execution timestamp must be a non-negative integer or None")
        elif execution_timestamp_ns is not None and execution_timestamp_ns < 0:
            issues.append("execution timestamp must be non-negative")
        if issues:
            self._issues.extend(f"action {issue}" for issue in issues)
            raise ValueError("invalid RoboChallenge action: " + "; ".join(issues))
        if message.action_id in self._action_ids:
            issue = f"duplicate action_id: {message.action_id}"
            self._issues.append(issue)
            raise ValueError(issue)
        self._action_ids.add(message.action_id)
        self._event_count += 1
        self.sink(
            {
                "event_type": "robochallenge_action_acknowledged",
                "adapter_sequence": self._event_count - 1,
                "action_id": message.action_id,
                "command_timestamp_ns": message.command_timestamp_ns,
                "execution_timestamp_ns": execution_timestamp_ns,
                "payload_base64": base64.b64encode(message.payload).decode("ascii"),
                "execution_timestamp_status": "reported"
                if execution_timestamp_ns is not None
                else "unavailable",
                "payload_digest_sha256": message.payload_digest_sha256,
            }
        )

    def audit(self) -> RoboChallengeProtocolAudit:
        """Return deterministic message accounting for the observed session."""
        return RoboChallengeProtocolAudit(
            len(self._observation_ids),
            len(self._action_ids),
            self._event_count,
            tuple(self._issues),
        )

    def _reject_wire(self, issue: str) -> None:
        self._issues.append(f"wire {issue}")
        raise ValueError(issue)


def audit_robochallenge_wire_records(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Audit canonical JSON-safe RoboChallenge records without scoring them.

    The adapter remains the sole protocol implementation. This helper only
    provides a deterministic, serializable report for mock/client traces and
    deliberately treats malformed records as sticky audit failures while
    continuing to inspect later records.
    """
    emitted: list[dict[str, object]] = []
    adapter = RoboChallengeObserveOnlyAdapter(emitted.append)
    for index, record in enumerate(records):
        try:
            adapter.ingest_record(record)
        except (TypeError, ValueError) as exc:
            adapter._issues.append(f"record {index}: {type(exc).__name__}: {exc}")
    audit = adapter.audit()
    return {
        "schema": "ival.robochallenge_protocol_audit.v1",
        "valid": audit.valid,
        "observation_count": audit.observation_count,
        "action_acknowledgment_count": audit.action_acknowledgment_count,
        "event_count": audit.event_count,
        "issues": list(audit.issues),
        "canonical_records": emitted,
        "execution_and_scoring": "external",
    }


def _wire_string(record: Mapping[str, Any], field: str) -> str:
    value = record[field]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _wire_non_negative_int(record: Mapping[str, Any], field: str) -> int:
    value = record[field]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _wire_payload(record: Mapping[str, Any]) -> bytes:
    value = record["payload_base64"]
    if not isinstance(value, str):
        raise ValueError("payload_base64 must be a string")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("payload_base64 is not valid base64") from exc
