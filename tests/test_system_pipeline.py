import pytest
import benchstudio as bs
from benchstudio.system_comparison import compare_system_runs
from benchstudio.system_pipeline import SystemEvaluationPipeline


def benchmark(**kwargs):
    return bs.Benchmark("arithmetic", "dataset-r1", [1, 2], [2, 4],
                        lambda output, target: bs.Score(output == target),
                        evaluator_revision="exact-r1", **kwargs)


def test_callable_agent_pipeline_is_inert_until_called_and_pairs_revisions():
    calls = []
    def composed(x):
        calls.append(x)
        world_prediction = x * 2
        return world_prediction
    a = bs.System.from_callable(composed, name="agent-with-world-model", revision="a")
    b = bs.System.from_callable(lambda x: x, name="agent-with-world-model", revision="b")
    data = benchmark(authoritative=True)
    pipe = bs.pipeline("evaluate", system=a, benchmark=data)
    assert calls == []
    baseline = pipe()
    candidate = bs.pipeline("evaluate", system=b, benchmark=data)()
    assert calls == [1, 2]
    comparison = compare_system_runs(baseline, candidate)
    assert comparison.valid_binary_pairs == 2
    assert comparison.paired_success.success_gap_b_minus_a == -1


def test_world_model_numeric_metrics_do_not_become_binary_outcomes():
    data = bs.Benchmark("forecast", "data-r1", [1], [3],
                        lambda output, target: bs.Score(metrics={"error": abs(output-target)}),
                        evaluator_revision="absolute-error-r1")
    system = bs.System.from_callable(lambda x: x+1, name="forecast-model", revision="r1")
    trial = bs.pipeline(system=system, benchmark=data)().trials[0]
    assert trial.metrics == {"error": 1}
    assert trial.success is None
    assert not trial.valid_success


def test_execution_error_propagates_instead_of_becoming_task_failure():
    def broken(_):
        raise RuntimeError("runtime failed")
    system = bs.System.from_callable(broken, name="agent", revision="r1")
    with pytest.raises(RuntimeError, match="runtime failed"):
        bs.pipeline(system=system, benchmark=benchmark())()


def test_benchmark_validated_before_execution_and_authority_is_explicit():
    with pytest.raises(ValueError, match="equal nonempty"):
        bs.Benchmark("t", "r", [], [], lambda a,b: bs.Score(), "r")
    system = bs.System.from_callable(lambda x: x*2, name="model", revision="r1")
    run = bs.pipeline(system=system, benchmark=benchmark())()
    assert run.trials[0].success is True
    assert not run.trials[0].valid_success
