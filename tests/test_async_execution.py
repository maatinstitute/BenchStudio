import asyncio
import pytest
import benchstudio as bs


def system(runtime, name="system"):
    return bs.System.from_callable(runtime, name=name, revision="r1")


def benchmark(n=4):
    return bs.Benchmark("test", "r1", list(range(n)), list(range(n)),
                        lambda a,b: bs.Score(a == b), evaluator_revision="exact-r1")


def test_bounded_overlap_and_stable_output_order():
    async def check():
        active = peak = 0
        gate = asyncio.Event()
        async def runtime(value):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                gate.set()
            await gate.wait()
            await asyncio.sleep(0)
            active -= 1
            return value
        pipe = bs.SystemEvaluationPipeline(system=system(runtime), benchmark=benchmark())
        run = await pipe.arun(concurrency=2)
        assert peak == 2
        assert [t.trial_id for t in run.trials] == ["0", "1", "2", "3"]
        assert all(t.success for t in run.trials)
    asyncio.run(check())


def test_resource_pool_serializes_agents_and_reducer_gets_named_outputs():
    async def check():
        active = peak = 0
        async def agent(value):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1
            return value + 1
        pool = bs.ResourcePool({"model": 1})
        group = bs.AgentGroup({"a": system(agent), "b": system(agent)},
                              reducer=lambda results: sum(results.values()), concurrency=2,
                              pool=pool, resources={"a": ("model",), "b": ("model",)})
        assert await group(2) == 6
        assert peak == 1
    asyncio.run(check())


def test_failure_cancels_and_drains_siblings_before_returning():
    async def check():
        started, cleaned = asyncio.Event(), asyncio.Event()
        async def fail(_):
            await started.wait()
            raise RuntimeError("agent failed")
        async def block(_):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        group = bs.AgentGroup({"fail": system(fail), "block": system(block)},
                              reducer=lambda x: x, concurrency=2)
        with pytest.raises(RuntimeError, match="agent failed"):
            await group(None)
        assert cleaned.is_set()
    asyncio.run(check())


def test_timeout_and_external_cancellation_release_resources():
    async def check():
        pool = bs.ResourcePool({"slot": 1})
        entered = asyncio.Event()
        async def runtime(_):
            async with pool.lease(("slot",)):
                entered.set()
                await asyncio.Event().wait()
        pipe = bs.SystemEvaluationPipeline(system=system(runtime), benchmark=benchmark(1))
        with pytest.raises(asyncio.TimeoutError):
            await pipe.arun(timeout=.01)
        async with pool.lease(("slot",)):
            pass
        entered.clear()
        task = asyncio.create_task(pipe.arun())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with pool.lease(("slot",)):
            pass
    asyncio.run(check())


def test_cancelled_partial_resource_lease_does_not_leak():
    async def check():
        pool = bs.ResourcePool({"a": 1, "b": 1})
        async with pool.lease(("b",)):
            async def wait():
                async with pool.lease(("a", "b")):
                    pass
            task = asyncio.create_task(wait())
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            async def check_released_slot():
                async with pool.lease(("a",)):
                    pass
            await asyncio.wait_for(asyncio.create_task(check_released_slot()), 1)
    asyncio.run(check())


def test_async_runtime_requires_async_entrypoint():
    async def runtime(value):
        return value
    pipe = bs.SystemEvaluationPipeline(system=system(runtime), benchmark=benchmark())
    with pytest.raises(TypeError, match="arun"):
        pipe.run()


def test_bad_limits_refused_before_runtime_calls():
    async def check():
        pipe = bs.SystemEvaluationPipeline(system=system(lambda x: pytest.fail("called")),
                                           benchmark=benchmark())
        with pytest.raises(ValueError):
            await pipe.arun(concurrency=0)
        for timeout in (0, float("nan"), True):
            with pytest.raises(ValueError):
                await pipe.arun(timeout=timeout)
        with pytest.raises(ValueError, match="unknown resource"):
            async with bs.ResourcePool({"x": 1}).lease(("missing",)):
                pass
    asyncio.run(check())


def test_async_scorer_and_security_controls():
    import runpy
    from pathlib import Path
    example = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                "examples/systems/agent_security.py"))
    score = example["score"]
    assert score({"executed": True}, {"tool": "read_secret"}).success is False
    assert score({"executed": False}, {"tool": "search_public_docs"}).success is False
    async def check():
        async def scorer(value, target):
            await asyncio.sleep(0)
            return bs.Score(value == target)
        data = bs.Benchmark("async-score", "r1", [1], [1], scorer, "r1")
        pipe = bs.SystemEvaluationPipeline(system=system(lambda x: x), benchmark=data)
        assert (await pipe.arun()).trials[0].success is True
        with pytest.raises(TypeError, match="async scorers"):
            pipe.run()
    asyncio.run(check())


def test_nested_resource_lease_refuses_instead_of_deadlocking():
    async def check():
        pool = bs.ResourcePool({"model": 1})
        async with pool.lease(("model",)):
            with pytest.raises(RuntimeError, match="nested"):
                async with pool.lease(("model",)):
                    pytest.fail("nested lease entered")
        async with pool.lease(("model",)):
            pass
    asyncio.run(check())
