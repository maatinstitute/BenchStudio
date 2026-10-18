from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from ..contracts import ActionChunk, Observation, Policy
from .action_semantics import ActionSpec, validate_action


class SessionStatus(str, Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class ModalityFrame:
    """A policy input frame with an explicit capture timestamp."""

    modality: str
    timestamp_ns: int
    payload_digest: str | None = None


@dataclass(frozen=True)
class PolicySessionEvent:
    session_id: str
    event: str
    status: SessionStatus
    code: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "session_id": self.session_id,
            "event": self.event,
            "status": self.status.value,
            "code": self.code,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class PredictionResult:
    status: str
    action_chunk: ActionChunk | None
    latency_ns: int | None
    errors: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"


@dataclass
class PolicySession:
    """Small, explicit policy-facing session boundary for adapters and runners.

    The boundary makes readiness, modality freshness, prediction validation, and
    failure/timeout outcomes evidence-bearing. It deliberately does not catch
    arbitrary exceptions as successful predictions.
    """

    session_id: str
    policy: Policy
    required_modalities: tuple[str, ...] = ()
    modality_max_age_ns: int | None = None
    action_spec: ActionSpec | None = None
    status: SessionStatus = SessionStatus.CREATED
    events: list[PolicySessionEvent] = field(default_factory=list)

    def initialize(self, *, seed: int) -> PolicySessionEvent:
        self._transition(SessionStatus.INITIALIZED, event="initialize", code="initialized")
        try:
            self.policy.reset(seed=seed)
        except Exception as exc:  # noqa: BLE001 - preserve failure as evidence
            self._fail("policy_reset_failed", repr(exc))
            raise
        return self.events[-1]

    def start(self) -> PolicySessionEvent:
        return self._transition(SessionStatus.RUNNING, event="start", code="running")

    def stop(self) -> PolicySessionEvent:
        if self.status == SessionStatus.STOPPED:
            return self._record("stop", "already_stopped", "Session was already stopped.")
        if self.status == SessionStatus.FAILED:
            return self._transition(
                SessionStatus.STOPPED, event="stop", code="stopped_after_failure"
            )
        return self._transition(SessionStatus.STOPPED, event="stop", code="stopped")

    def validate_modalities(
        self,
        frames: tuple[ModalityFrame, ...] | list[ModalityFrame],
        *,
        now_ns: int | None = None,
    ) -> list[str]:
        """Return missing, stale, duplicate, and future-frame errors."""
        current = time.monotonic_ns() if now_ns is None else now_ns
        by_name: dict[str, list[ModalityFrame]] = {}
        errors: list[str] = []
        for frame in frames:
            by_name.setdefault(frame.modality, []).append(frame)
            if frame.timestamp_ns > current:
                errors.append(f"{frame.modality} frame is from the future")
        for modality in self.required_modalities:
            candidates = by_name.get(modality, [])
            if not candidates:
                errors.append(f"missing required modality: {modality}")
                continue
            if len(candidates) > 1:
                errors.append(f"duplicate modality frame: {modality}")
            if self.modality_max_age_ns is not None:
                age = current - max(frame.timestamp_ns for frame in candidates)
                if age > self.modality_max_age_ns:
                    errors.append(f"stale modality frame: {modality} age_ns={age}")
        return errors

    def predict(
        self,
        observation: Observation,
        *,
        denoising_steps: int | None = None,
        frames: tuple[ModalityFrame, ...] | list[ModalityFrame] = (),
        now_ns: int | None = None,
        timeout_ns: int | None = None,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> PredictionResult:
        if self.status != SessionStatus.RUNNING:
            return self._rejected("invalid_session_state", f"session is {self.status.value}")
        modality_errors = self.validate_modalities(frames, now_ns=now_ns)
        if modality_errors:
            return self._rejected("invalid_modalities", "; ".join(modality_errors), modality_errors)
        started = clock_ns()
        try:
            result = self.policy.predict(observation, denoising_steps=denoising_steps)
        except TimeoutError as exc:
            return self._rejected("prediction_timeout", str(exc), latency_ns=clock_ns() - started)
        except Exception as exc:  # noqa: BLE001 - adapter must expose policy failure
            self._fail("prediction_failed", repr(exc))
            return self._rejected("prediction_failed", repr(exc), latency_ns=clock_ns() - started)
        latency = clock_ns() - started
        if timeout_ns is not None and latency > timeout_ns:
            return self._rejected(
                "deadline_missed",
                f"latency_ns={latency} > timeout_ns={timeout_ns}",
                latency_ns=latency,
            )
        if not isinstance(result, ActionChunk):
            return self._rejected(
                "invalid_prediction",
                "policy did not return ActionChunk",
                latency_ns=latency,
            )
        if self.action_spec is not None:
            errors = tuple(validate_action(result.actions, self.action_spec))
            if errors:
                return self._rejected("invalid_action", "; ".join(errors), errors, latency)
        return PredictionResult("accepted", result, latency)

    def _transition(self, target: SessionStatus, *, event: str, code: str) -> PolicySessionEvent:
        allowed = {
            SessionStatus.CREATED: {SessionStatus.INITIALIZED, SessionStatus.FAILED},
            SessionStatus.INITIALIZED: {
                SessionStatus.RUNNING,
                SessionStatus.STOPPED,
                SessionStatus.FAILED,
            },
            SessionStatus.RUNNING: {SessionStatus.STOPPED, SessionStatus.FAILED},
            SessionStatus.FAILED: {SessionStatus.STOPPED},
            SessionStatus.STOPPED: set(),
        }
        if target not in allowed[self.status]:
            raise ValueError(f"invalid session transition: {self.status.value} -> {target.value}")
        self.status = target
        return self._record(event, code, "")

    def _record(self, event: str, code: str, detail: str) -> PolicySessionEvent:
        item = PolicySessionEvent(self.session_id, event, self.status, code, detail)
        self.events.append(item)
        return item

    def _fail(self, code: str, detail: str) -> None:
        if self.status != SessionStatus.FAILED:
            self._transition(SessionStatus.FAILED, event="failure", code=code)
        else:
            self._record("failure", code, detail)

    def _rejected(
        self,
        status: str,
        detail: str,
        errors: list[str] | tuple[str, ...] = (),
        latency_ns: int | None = None,
    ) -> PredictionResult:
        return PredictionResult(status, None, latency_ns, tuple(errors) or (detail,))
