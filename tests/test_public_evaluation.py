"""Researcher entry point: no backend contract or per-case execution method."""
import pytest

import benchstudio as bs


@pytest.mark.parametrize("task", [None, "evaluate"])
def test_callable_public_pipeline_preserves_results_and_retention(tmp_path, task):
    calls = []
    system = bs.System.from_callable(lambda value: calls.append(value) or 2 * value,
                                    name="synthetic-system", revision="r1")
    benchmark = bs.Benchmark("arithmetic", "r1", [1, 2], [2, 4],
                            lambda output, target: bs.Score(success=output == target), "r1")
    options = dict(system=system, benchmark=benchmark,
                   config=bs.EvaluationConfig(output_dir=tmp_path / "out"))
    evaluation = bs.pipeline(**options) if task is None else bs.pipeline(task, **options)
    assert evaluation.check().configuration_valid and calls == []
    results = evaluation()
    assert calls == [1, 2] and all(trial.success for trial in results.trials)
    retained = bs.open_run(tmp_path / "out")
    assert retained.trials == results.trials


def test_backend_extension_types_are_not_top_level_researcher_api():
    assert "ExecutionBackend" not in bs.__all__ and not hasattr(bs, "ExecutionBackend")
    assert "CaseResult" not in bs.__all__ and not hasattr(bs, "CaseResult")
