from contextlib import contextmanager
import pytest
import benchstudio as bs


def test_reset_runs_before_each_episode_and_failure_prevents_body():
    state = [99]
    isolation = bs.EpisodeIsolation(reset=lambda system, case: system.clear())
    for case in ("a", "b"):
        with isolation.activate(state, case) as system:
            assert system == []
            system.append(4)
    def fail(*args):
        raise RuntimeError("reset failed")
    with pytest.raises(RuntimeError), bs.EpisodeIsolation(reset=fail).activate(state, "a"):
        pytest.fail("must not enter")


def test_factory_cleanup_on_episode_exception():
    events = []
    @contextmanager
    def factory(case):
        events.append(case)
        try:
            yield object()
        finally:
            events.append("closed")
    with pytest.raises(RuntimeError), bs.EpisodeIsolation(factory=factory).activate(None, "a"):
        raise RuntimeError("episode error")
    assert events == ["a", "closed"]


def test_trace_preserves_proposals_and_truncation_immutably():
    observation = {"tick": 1}
    proposed = [{"delta": 1}, {"delta": 2}]
    batch = bs.ActionBatch(observation, proposed, (0,))
    observation["tick"] = 5
    proposed.clear()
    assert batch.to_dict() == {"observation": {"tick": 1},
        "proposed": [{"delta": 1}, {"delta": 2}], "applied_indices": [0]}
    for indices in ((2,), (0, 0), (1, 0)):
        with pytest.raises(ValueError):
            bs.ActionBatch({}, (1, 2), indices)


def test_outcome_and_coverage_are_independent():
    outcome = bs.EpisodeOutcome(True, True, False)
    assert outcome.completed and outcome.goal_reached and not outcome.constraints_satisfied
    assert bs.EpisodeOutcome(True).constraints_satisfied is None
    assert bs.EpisodeCoverage(("a", "b"), ("a",)).missing == ("b",)
    with pytest.raises(ValueError):
        bs.EpisodeCoverage(("a",), ("b",))
    with pytest.raises(ValueError):
        bs.EpisodeIsolation()


def test_engine_retains_grouped_native_evidence_and_reports_missing(tmp_path):
    from types import SimpleNamespace
    from benchstudio.backends import CaseResult, BenchmarkCase
    class Protocol:
        cases = (BenchmarkCase("a", {}, "job"), BenchmarkCase("b", {}, "job"))
        supports_retries = False
        def bind(self, system, *, benchmark, config):
            return SimpleNamespace(cases=("job",), supports_timeout=False,
                check=lambda config: (), start=lambda config: None,
                execute_case=lambda *a, **k: CaseResult(True, "native-result", (
                    bs.EpisodeRecord("a", bs.EpisodeOutcome(True, False, None)),)),
                record=lambda *a, **k: None, close=lambda: None, finish=lambda: "native-result")
    plan = bs.Benchmark("fixture", "r1", protocol=Protocol(),
        evaluator_revision="e1", environment_revision="env1")
    pipeline = bs.pipeline(system=object(), benchmark=plan,
        config=bs.EvaluationConfig(output_dir=tmp_path / "out"))
    assert pipeline() == "native-result"  # No wrapper around the native result.
    assert pipeline.episode_coverage.missing == ("b",)
    import json
    saved = json.loads((tmp_path / "out/episodes.jsonl").read_text())
    assert saved["case_id"] == "a" and saved["execution_id"] == "job"
    assert saved["outcome"]["goal_reached"] is False
    coverage = json.loads((tmp_path / "out/episode_coverage.json").read_text())
    assert coverage["missing"] == ["b"]
    assert not saved["isolation_verified"]


def test_engine_refuses_cross_group_and_duplicate_evidence(tmp_path):
    from types import SimpleNamespace
    from benchstudio.backends import CaseResult
    for bad_id in ("wrong", "a"):
        backend = SimpleNamespace(cases=("a", "b"), supports_timeout=False,
            check=lambda config: (), start=lambda config: None,
            execute_case=lambda *a, **k: CaseResult(True, episodes=(
                bs.EpisodeRecord(bad_id, bs.EpisodeOutcome(True)),)),
            record=lambda *a, **k: None, close=lambda: None, finish=lambda: None)
        pipeline = bs.EvaluationEngine(backend=backend)
        with pytest.raises(ValueError, match="execution group"):
            pipeline()
    with pytest.raises(ValueError, match="duplicate"):
        CaseResult(True, episodes=(bs.EpisodeRecord("a", bs.EpisodeOutcome(True)),) * 2)


def test_failed_run_retains_partial_coverage_and_always_closes(tmp_path):
    from types import SimpleNamespace
    from benchstudio.backends import CaseResult
    closed = []
    def execute(case, **kwargs):
        if case == "b":
            raise RuntimeError("native error")
        return CaseResult(True, episodes=(bs.EpisodeRecord(case, bs.EpisodeOutcome(True)),))
    backend = SimpleNamespace(cases=("a", "b"), supports_timeout=False,
        check=lambda config: (), start=lambda config: None, execute_case=execute,
        record=lambda *a, **k: None, close=lambda: closed.append(True), finish=lambda: None)
    pipeline = bs.EvaluationEngine(backend=backend,
        config=bs.EvaluationConfig(output_dir=tmp_path / "failed"))
    with pytest.raises(RuntimeError, match="native error"):
        pipeline()
    assert closed == [True] and pipeline.episode_coverage.missing == ("b",)
    import json
    assert json.loads((tmp_path / "failed/episode_coverage.json").read_text())["missing"] == ["b"]
