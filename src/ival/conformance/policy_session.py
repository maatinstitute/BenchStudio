from __future__ import annotations

import asyncio
import inspect
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal

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
    execution_strategy: str = "sync"
    cache_hit: bool = False

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
    execution_strategy: Literal["sync", "async", "streaming", "cached"] = "sync"
    max_cache_entries: int = 256
    status: SessionStatus = SessionStatus.CREATED
    events: list[PolicySessionEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.execution_strategy not in {"sync", "async", "streaming", "cached"}:
            raise ValueError(f"unsupported execution strategy: {self.execution_strategy}")
        if self.max_cache_entries < 1:
            raise ValueError("max_cache_entries must be positive")
        self._prediction_cache: dict[str, ActionChunk] = {}

    def initialize(self, *, seed: int) -> PolicySessionEvent:
        self._transition(SessionStatus.INITIALIZED, event="initialize", code="initialized")
        try:
            self.policy.reset(seed=seed)
            self._prediction_cache.clear()
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
        cache_hit = False
        try:
            cache_key = self._cache_key(observation, denoising_steps)
            if self.execution_strategy == "cached" and cache_key in self._prediction_cache:
                result = self._prediction_cache[cache_key]
                cache_hit = True
            else:
                result = self._invoke(observation, denoising_steps, timeout_ns)
                if self.execution_strategy == "cached":
                    if len(self._prediction_cache) >= self.max_cache_entries:
                        self._prediction_cache.pop(next(iter(self._prediction_cache)))
                    self._prediction_cache[cache_key] = result
        except (TimeoutError, FutureTimeoutError) as exc:
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
        return PredictionResult(
            "accepted",
            result,
            latency,
            execution_strategy=self.execution_strategy,
            cache_hit=cache_hit,
        )

    def _invoke(
        self, observation: Observation, denoising_steps: int | None, timeout_ns: int | None
    ) -> Any:
        if self.execution_strategy == "sync" or self.execution_strategy == "cached":
            return self.policy.predict(observation, denoising_steps=denoising_steps)
        if self.execution_strategy == "streaming":
            stream = getattr(self.policy, "predict_stream", None)
            if stream is None:
                raise RuntimeError("streaming execution requires policy.predict_stream")
            values = stream(observation, denoising_steps=denoising_steps)
            if inspect.isawaitable(values):
                values = _resolve_awaitable(values)
            if isinstance(values, ActionChunk):
                return values
            if hasattr(values, "__aiter__"):
                return _first_async_value(values)
            for value in values:
                if isinstance(value, ActionChunk):
                    return value
            raise RuntimeError("policy.predict_stream produced no ActionChunk")
        method = getattr(self.policy, "predict_async", self.policy.predict)
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ival-policy")
        future = pool.submit(
            _invoke_async_method, method, observation, denoising_steps=denoising_steps
        )
        timeout_s = None if timeout_ns is None else timeout_ns / 1_000_000_000
        timed_out = False
        try:
            return future.result(timeout=timeout_s)
        except TimeoutError:
            timed_out = True
            raise
        finally:
            pool.shutdown(wait=not timed_out, cancel_futures=timed_out)

    @staticmethod
    def _cache_key(observation: Observation, denoising_steps: int | None) -> str:
        import hashlib
        import json

        payload = json.dumps(
            {
                "sequence": observation.sequence,
                "sim_time_s": observation.sim_time_s,
                "payload": observation.payload,
                "denoising_steps": denoising_steps,
            },
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

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
        return PredictionResult(
            status,
            None,
            latency_ns,
            tuple(errors) or (detail,),
            execution_strategy=self.execution_strategy,
        )


def _invoke_async_method(
    method: Callable[..., Any], observation: Observation, **kwargs: Any
) -> Any:
    return _resolve_awaitable(method(observation, **kwargs))


def _resolve_awaitable(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    return asyncio.run(value)


def _first_async_value(values: Any) -> Any:
    async def consume() -> Any:
        async for value in values:
            if isinstance(value, ActionChunk):
                return value
        return None

    result = asyncio.run(consume())
    if result is None:
        raise RuntimeError("policy.predict_stream produced no ActionChunk")
    return result
