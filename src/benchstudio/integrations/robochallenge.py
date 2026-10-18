from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable


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


def validate_robochallenge_message(
    message: RoboChallengeObservation | RoboChallengeAction,
) -> list[str]:
    issues: list[str] = []
    if (
        not message.observation_id
        if isinstance(message, RoboChallengeObservation)
        else not message.action_id
    ):
        issues.append("message identifier is required")
    if (
        message.timestamp_ns < 0
        if isinstance(message, RoboChallengeObservation)
        else message.command_timestamp_ns < 0
    ):
        issues.append("message timestamp must be non-negative")
    expected = hashlib.sha256(message.payload).hexdigest()
    if expected != message.payload_digest_sha256:
        issues.append("payload digest mismatch")
    return issues


class RoboChallengeObserveOnlyAdapter:
    """Record protocol messages while leaving execution and official scoring external."""

    def __init__(self, sink: Callable[[dict[str, object]], None]) -> None:
        self.sink = sink

    def observe(self, message: RoboChallengeObservation) -> None:
        issues = validate_robochallenge_message(message)
        if issues:
            raise ValueError("invalid RoboChallenge observation: " + "; ".join(issues))
        self.sink(
            {
                "event_type": "robochallenge_observation",
                "observation_id": message.observation_id,
                "timestamp_ns": message.timestamp_ns,
                "payload_digest_sha256": message.payload_digest_sha256,
            }
        )

    def action_acknowledged(
        self, message: RoboChallengeAction, *, execution_timestamp_ns: int | None
    ) -> None:
        issues = validate_robochallenge_message(message)
        if issues:
            raise ValueError("invalid RoboChallenge action: " + "; ".join(issues))
        self.sink(
            {
                "event_type": "robochallenge_action_acknowledged",
                "action_id": message.action_id,
                "command_timestamp_ns": message.command_timestamp_ns,
                "execution_timestamp_ns": execution_timestamp_ns,
                "execution_timestamp_status": "reported"
                if execution_timestamp_ns is not None
                else "unavailable",
                "payload_digest_sha256": message.payload_digest_sha256,
            }
        )
