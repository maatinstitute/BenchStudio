import json
from types import SimpleNamespace
import pytest
import benchstudio as bs
from benchstudio.backends import BenchmarkCase, CaseResult


def test_supported_surface_is_small_and_has_no_dynamic_reexports():
    assert len(bs.__all__) == 15
    assert all(hasattr(bs, name) for name in bs.__all__)
    assert "EpisodeRecord" in bs.__all__ and "ProcessCommand" not in bs.__all__
    assert "__getattr__" not in vars(bs)
    assert not hasattr(bs, "ProcessCommand")
    from benchstudio.processes import ProcessCommand
    assert ProcessCommand.__module__ == "benchstudio.processes"
    assert bs.__version__ == "0.1.0rc2"


def test_integrations_require_an_explicit_module_import():
    import benchstudio.integrations as integrations
    assert "__getattr__" not in vars(integrations)
    assert not hasattr(integrations, "FixedReference")
    from benchstudio.integrations.robopad_reference import FixedReference
    assert FixedReference.__module__ == "benchstudio.integrations.robopad_reference"


def test_old_loader_and_task_aliases_are_absent():
    assert not hasattr(bs.System, "from_pretrained")
    assert not hasattr(bs.Benchmark, "from_pretrained")
    assert not hasattr(bs.System, "from_vllm")
    with pytest.raises(ValueError, match="unsupported BenchStudio pipeline task"):
        bs.pipeline("system-evaluation")


def test_offline_report_preserves_metrics_units_and_native_result(tmp_path):
    plan = bs.Benchmark("arithmetic", "r1", [2], [4],
        lambda a, b: bs.Score(a == b, {"distance_m": abs(a-b)}), "e1")
    evaluation = bs.pipeline(system=bs.System.from_callable(lambda x: x*2, name="double", revision="r1"),
        benchmark=plan, config=bs.EvaluationConfig(output_dir=tmp_path / "run"))
    assert evaluation.check().capabilities == evaluation.capabilities
    with pytest.raises(RuntimeError):
        evaluation.report()
    native = evaluation()
    report = evaluation.report()
    assert report.native is native and not report.coverage.missing
    assert list(report.metrics.values())[0]["distance_m"] == 0
    retained = bs.inspect_result(bs.open_run(tmp_path / "run"))
    assert retained.coverage == report.coverage and retained.summary() == report.summary()


def test_protocol_capabilities_and_unknown_native_coverage_are_honest(tmp_path):
    closed = []
    class Protocol:
        cases = (BenchmarkCase("a", {}, "job"), BenchmarkCase("b", {}, "job"))
        def bind(self, system, *, benchmark, config):
            return SimpleNamespace(cases=("job",), supports_timeout=False,
                check=lambda config: (), start=lambda config: None,
                execute_case=lambda *a, **k: CaseResult(True, episodes=(
                    bs.EpisodeRecord("a", bs.EpisodeOutcome(True, True, None)),)),
                record=lambda *a, **k: None, close=lambda: closed.append(True),
                finish=lambda: SimpleNamespace(summary=lambda: "native"))
    plan = bs.Benchmark("fixture", "r1", protocol=Protocol(), evaluator_revision="e1", environment_revision="env1")
    evaluation = bs.pipeline(system=object(), benchmark=plan)
    assert evaluation.check().capabilities["batching"] is False
    assert not evaluation.capabilities["async"] and not evaluation.capabilities["timeout"]
    assert not evaluation.check(mode="async").configuration_valid
    assert not closed
    native = evaluation()
    assert evaluation.report().coverage.missing == ("b",)
    assert evaluation.report().outcomes["a"].constraints_satisfied is None
    assert bs.inspect_result(native).coverage is None
    assert evaluation.report().native is native and closed == [True]


def test_common_inspector_rejects_duplicate_unbound_native_records():
    episode = bs.EpisodeRecord("a", bs.EpisodeOutcome(True))
    with pytest.raises(ValueError, match="duplicate episode"):
        bs.inspect_result(object(), episodes=(episode, episode))


def test_async_scorer_capabilities_refuse_sync_before_execution():
    async def scorer(a, b):
        return bs.Score(success=a == b)
    plan = bs.Benchmark("fixture", "r1", [1], [1], scorer, "e1")
    evaluation = bs.pipeline(system=bs.System.from_callable(lambda x: x, name="identity", revision="r1"), benchmark=plan)
    assert not evaluation.capabilities["sync"]
    assert not evaluation.check().configuration_valid
    assert evaluation.check(mode="async").configuration_valid


def test_dashboard_requires_an_explicit_study_definition(tmp_path):
    from benchstudio.demo_dashboard import build_demo_dashboard

    with pytest.raises(FileNotFoundError, match="study definition is required"):
        build_demo_dashboard(tmp_path, tmp_path / "dashboard.html")
    assert not (tmp_path / "dashboard.html").exists()
