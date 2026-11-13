from dataclasses import dataclass

from reva.conformance import (
    ActionSpec,
    ModalityFrame,
    PolicySession,
    SessionStatus,
)
from reva.contracts import ActionChunk, Observation


@dataclass
class StubPolicy:
    result: object = ActionChunk((0.1, 0.2))

    def reset(self, *, seed: int) -> None:
        self.seed = seed

    def predict(self, observation: Observation, *, denoising_steps: int | None) -> ActionChunk:
        return self.result  # type: ignore[return-value]


def _session(policy: StubPolicy | None = None) -> PolicySession:
    return PolicySession(
        "session-a",
        policy or StubPolicy(),
        required_modalities=("image", "state"),
        modality_max_age_ns=100,
        action_spec=ActionSpec("arm", "joint_position", "rad", 2),
    )


def test_policy_session_requires_explicit_lifecycle() -> None:
    session = _session()
    result = session.predict(Observation(0, 0.0))
    assert result.status == "invalid_session_state"
    session.initialize(seed=7)
    session.start()
    assert session.status == SessionStatus.RUNNING


def test_policy_session_rejects_missing_and_stale_modalities() -> None:
    session = _session()
    session.initialize(seed=1)
    session.start()
    result = session.predict(
        Observation(0, 0.0),
        frames=[ModalityFrame("image", 850), ModalityFrame("image", 990)],
        now_ns=1_000,
    )
    assert result.status == "invalid_modalities"
    assert any("missing required modality" in error for error in result.errors)
    assert any("duplicate modality" in error for error in result.errors)


def test_policy_session_validates_action_and_deadline() -> None:
    session = _session()
    session.initialize(seed=1)
    session.start()
    clock = iter((100, 250))
    result = session.predict(
        Observation(0, 0.0),
        frames=[ModalityFrame("image", 990), ModalityFrame("state", 995)],
        now_ns=1_000,
        timeout_ns=100,
        clock_ns=lambda: next(clock),
    )
    assert result.status == "deadline_missed"
    assert result.latency_ns == 150


def test_policy_session_rejects_bad_action_shape() -> None:
    session = _session(StubPolicy(ActionChunk((0.1,))))
    session.initialize(seed=1)
    session.start()
    result = session.predict(
        Observation(0, 0.0),
        frames=[ModalityFrame("image", 990), ModalityFrame("state", 995)],
        now_ns=1_000,
    )
    assert result.status == "invalid_action"


def test_policy_session_cached_strategy_reuses_identical_prediction() -> None:
    class CountingPolicy(StubPolicy):
        calls = 0

        def predict(self, observation, *, denoising_steps):
            self.calls += 1
            return super().predict(observation, denoising_steps=denoising_steps)

    policy = CountingPolicy()
    session = PolicySession("cached", policy, execution_strategy="cached")
    session.initialize(seed=1)
    session.start()
    first = session.predict(Observation(0, 0.0), denoising_steps=2)
    second = session.predict(Observation(0, 0.0), denoising_steps=2)
    assert first.accepted and second.accepted
    assert second.cache_hit is True
    assert policy.calls == 1


def test_policy_session_streaming_strategy_requires_and_consumes_stream() -> None:
    class StreamingPolicy(StubPolicy):
        def predict_stream(self, observation, *, denoising_steps):
            yield ActionChunk((0.1, 0.2))

    session = PolicySession("streaming", StreamingPolicy(), execution_strategy="streaming")
    session.initialize(seed=1)
    session.start()
    result = session.predict(Observation(0, 0.0))
    assert result.accepted
    assert result.execution_strategy == "streaming"


def test_policy_session_async_strategy_uses_async_method() -> None:
    class AsyncPolicy(StubPolicy):
        def predict_async(self, observation, *, denoising_steps):
            return ActionChunk((0.1, 0.2))

    session = PolicySession("async", AsyncPolicy(), execution_strategy="async")
    session.initialize(seed=1)
    session.start()
    result = session.predict(Observation(0, 0.0))
    assert result.accepted
    assert result.execution_strategy == "async"


def test_policy_session_async_strategy_awaits_coroutine_method() -> None:
    class AsyncPolicy(StubPolicy):
        async def predict_async(self, observation, *, denoising_steps):
            return ActionChunk((0.1, 0.2))

    session = PolicySession("async-coroutine", AsyncPolicy(), execution_strategy="async")
    session.initialize(seed=1)
    session.start()
    result = session.predict(Observation(0, 0.0))
    assert result.accepted


def test_policy_session_streaming_strategy_consumes_async_stream() -> None:
    class AsyncStreamingPolicy(StubPolicy):
        async def predict_stream(self, observation, *, denoising_steps):
            yield ActionChunk((0.1, 0.2))

    session = PolicySession(
        "streaming-async", AsyncStreamingPolicy(), execution_strategy="streaming"
    )
    session.initialize(seed=1)
    session.start()
    result = session.predict(Observation(0, 0.0))
    assert result.accepted


def test_policy_session_async_deadline_does_not_wait_for_worker() -> None:
    import time

    class SlowPolicy(StubPolicy):
        def predict_async(self, observation, *, denoising_steps):
            time.sleep(0.05)
            return ActionChunk((0.1, 0.2))

    session = PolicySession("async-timeout", SlowPolicy(), execution_strategy="async")
    session.initialize(seed=1)
    session.start()
    started = time.monotonic()
    result = session.predict(Observation(0, 0.0), timeout_ns=1_000_000)
    elapsed = time.monotonic() - started
    assert result.status == "prediction_timeout"
    assert elapsed < 0.1
