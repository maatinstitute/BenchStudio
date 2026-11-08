import asyncio
import pytest
import benchstudio as bs


def build(runtime, config=None):
    system = bs.System.from_callable(runtime, name="composed-agent", revision="r1")
    benchmark = bs.Benchmark("task", "data-r1", [1, 2], [2, 4],
                             lambda output, target: bs.Score(output == target), "scorer-r1")
    return bs.pipeline("system-evaluation", system=system, benchmark=benchmark, config=config)


def test_shared_engine_is_inert_and_preserves_trial_identity():
    calls = []
    pipe = build(lambda x: calls.append(x) or x * 2, bs.EvaluationConfig(run_id="paired"))
    assert isinstance(pipe, bs.EvaluationEngine)
    check = pipe.check()
    assert check.configuration_valid and not check.native_verified and calls == []
    result = pipe.run()
    assert result.run_id == "paired" and calls == [1, 2]
    assert all(t.success for t in result.trials)


def test_batches_are_dispatched_to_existing_backend():
    class Runtime:
        def __call__(self, value):
            pytest.fail("scalar path used")
        def generate_batch(self, values):
            return [x * 2 for x in values]
    pipe = build(Runtime(), bs.EvaluationConfig(batch_size=2))
    assert pipe.check().configuration_valid
    assert all(t.success for t in pipe.run().trials)
    assert not pipe.check(mode="async").configuration_valid
    with pytest.raises(ValueError, match="batching"):
        asyncio.run(pipe.arun())


def test_async_configuration_is_honored_without_silent_sync_fallback():
    calls = []
    async def runtime(x):
        calls.append(x)
        return x * 2
    pipe = build(runtime, bs.EvaluationConfig(concurrency=2, timeout=2))
    assert not pipe.check().configuration_valid
    assert pipe.check(mode="async").configuration_valid and calls == []
    with pytest.raises(ValueError, match="arun"):
        pipe.run()
    assert calls == []
    assert all(t.success for t in asyncio.run(pipe.arun()).trials)


@pytest.mark.parametrize("options", [{"batch_size": True}, {"concurrency": 0},
                                     {"timeout": float("nan")}, {"run_id": ""}])
def test_invalid_configuration_rejected(options):
    with pytest.raises(ValueError):
        bs.EvaluationConfig(**options)
