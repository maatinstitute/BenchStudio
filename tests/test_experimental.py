import asyncio
from dataclasses import FrozenInstanceError
import pytest
import benchstudio as bs
from benchstudio.experimental import Workflow


def system(fn, name="component", revision="r1"):
    return bs.System.from_callable(fn, name=name, revision=revision)


def workflows(reference=lambda x: x, candidate=lambda x: x*2):
    base = Workflow("forecast-agent", "r1", {
        "predictor": system(reference, "predictor"),
        "planner": system(lambda x: x, "planner"),
    })
    variant = base.replace("predictor", system(candidate, "predictor", "r2"), revision="r2")
    return base, variant


def benchmark(inputs=(1, 2), targets=(2, 4), scorer=None):
    return bs.Benchmark("synthetic", "dataset-r1", inputs, targets,
                        scorer or (lambda a,b: bs.Score(a == b)), "scorer-r1", authoritative=True)


def study(a, b, data=None, **kwargs):
    return bs.pipeline("ablation", reference=a.as_system(), candidate=b.as_system(),
                       benchmark=data or benchmark(), changed_components=("predictor",), **kwargs)


def test_executable_component_replacement_and_paired_summary():
    a, b = workflows()
    result = asyncio.run(study(a, b).arun())
    assert result.comparison.valid_binary_pairs == 2
    assert result.summary()["success_delta"] == 1
    assert a.stages["planner"] is b.stages["planner"]
    assert a.spec.connections == b.spec.connections
    assert result.isolation.changed_components == ("predictor",)
    assert [t.key for t in result.reference.trials] == [t.key for t in result.candidate.trials]
    assert result.comparison.interpretation.startswith("DESCRIPTIVE")


def test_unapproved_change_is_refused_before_any_execution():
    a, b = workflows(lambda x: pytest.fail("executed"))
    b = b.replace("planner", system(lambda x: x, "planner", "r2"), revision="r3")
    with pytest.raises(ValueError, match="not isolated"):
        study(a, b)


def test_arm_order_alternates_and_inputs_are_not_shared_between_arms():
    seen = []
    def reference(value):
        seen.append("reference")
        value.append(9)
        return len(value)
    def candidate(value):
        seen.append("candidate")
        return len(value)
    a, b = workflows(reference, candidate)
    inputs = [[1], [2]]
    result = asyncio.run(study(a, b, benchmark(inputs, [1, 1])).arun())
    assert seen == ["reference", "candidate", "candidate", "reference"]
    assert inputs == [[1], [2]]
    assert result.arm_order == (("reference", "candidate"), ("candidate", "reference"))
    assert all(t.success is True for t in result.candidate.trials)
    assert all(t.success is False for t in result.reference.trials)


def test_continuous_only_world_model_comparison():
    a, b = workflows()
    data = benchmark(scorer=lambda a,b: bs.Score(metrics={"absolute_error": abs(a-b)}))
    result = asyncio.run(study(a, b, data, metrics=("absolute_error",)).arun())
    assert result.comparison.valid_binary_pairs == 0
    assert result.summary()["numeric_deltas"]["absolute_error"] == -1.5


def test_async_failure_is_propagated_not_scored_as_model_failure():
    async def broken(value):
        raise RuntimeError("backend disconnected")
    a, b = workflows(candidate=broken)
    with pytest.raises(RuntimeError, match="backend disconnected"):
        asyncio.run(study(a, b).arun())


def test_workflow_identity_cannot_be_rewired_after_construction():
    a, _ = workflows()
    with pytest.raises(TypeError):
        a.stages["extra"] = system(lambda x: x)
    with pytest.raises(FrozenInstanceError):
        a.stages = {}
    with pytest.raises(ValueError, match="unknown"):
        a.replace("missing", system(lambda x: x), revision="r2")


def test_analysis_and_execution_limits_validated_before_execution():
    a, b = workflows(lambda x: pytest.fail("executed"))
    with pytest.raises(ValueError, match="duplicate"):
        study(a, b, metrics=("loss", "loss"))
    with pytest.raises(ValueError, match="concurrency"):
        asyncio.run(study(a, b).arun(concurrency=0))
    with pytest.raises(ValueError, match="timeout"):
        asyncio.run(study(a, b).arun(timeout=float("nan")))
