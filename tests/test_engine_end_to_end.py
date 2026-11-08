import asyncio
from importlib import metadata
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import benchstudio as bs
import benchstudio.backend_loading as backend_loading
from benchstudio.system_cli import main


def recipe(revision="data-r1"):
    return bs.Benchmark("test", revision, [1, 2], [2, 4],
                        lambda output, target: bs.Score(output == target), "score-r1")


def install(monkeypatch, factory):
    benchmark = lambda **kw: recipe(kw["revision"])
    def entry_points(*, group, name):
        if name != "demo":
            return []
        return [SimpleNamespace(load=lambda: factory if group == "benchstudio.systems" else benchmark)]
    monkeypatch.setattr(backend_loading.metadata, "entry_points", entry_points)


def test_named_backend_pipeline_retains_reopenable_evidence(tmp_path, monkeypatch):
    calls = []
    install(monkeypatch, lambda revision: bs.System.from_callable(
        lambda x: calls.append(x) or x * 2, name="agent+world", revision=revision))
    system = bs.System.from_backend("demo", revision="system-r1")
    benchmark = bs.Benchmark.load("demo", revision="data-r1")
    pipe = bs.pipeline("evaluate", system=system, benchmark=benchmark,
                       config=bs.EvaluationConfig(output_dir=tmp_path / "run"))
    assert pipe.check().configuration_valid and calls == []
    result = pipe.run()
    retained = bs.open_run(tmp_path / "run")
    assert retained.trials == result.trials and all(t.success for t in result.trials)
    assert "2/2 completed" in result.summary()
    assert json.loads((tmp_path / "run/execution.json").read_text())["status"] == "completed"
    with pytest.raises(FileExistsError):
        pipe.run()
    assert calls == [1, 2]


def test_cli_check_and_execute_use_same_recipe_and_engine(tmp_path, monkeypatch, capsys):
    calls = []
    install(monkeypatch, lambda revision: bs.System.from_callable(
        lambda x: calls.append(x) or x * 2, name="swarm", revision=revision))
    args = ["--system", "demo", "--system-revision", "sys-r1", "--benchmark", "demo",
            "--benchmark-revision", "data-r1", "--output", str(tmp_path / "run")]
    assert main(args + ["--check"]) == 0
    assert calls == [] and not (tmp_path / "run").exists()
    assert main(args) == 0 and calls == [1, 2]
    assert len(bs.open_run(tmp_path / "run").trials) == 2


def test_missing_dependency_refuses_without_execution_or_output(tmp_path):
    class Runtime:
        requirements = {"missing_backend_distribution_synthetic": None}
        def __call__(self, x):
            pytest.fail("backend executed")
    pipe = bs.pipeline("evaluate", system=bs.System.from_callable(
        Runtime(), name="test", revision="r1"), benchmark=recipe(),
        config=bs.EvaluationConfig(output_dir=tmp_path / "run"))
    assert "missing dependency" in pipe.check().issues[0]
    with pytest.raises(TypeError, match="missing dependency"):
        pipe.run()
    assert not (tmp_path / "run").exists()


def test_failure_is_retained_without_inventing_scientific_outcomes(tmp_path):
    def broken(x):
        raise RuntimeError("backend failed")
    pipe = bs.pipeline("evaluate", system=bs.System.from_callable(
        broken, name="test", revision="r1"), benchmark=recipe(),
        config=bs.EvaluationConfig(output_dir=tmp_path / "run"))
    with pytest.raises(RuntimeError, match="backend failed"):
        pipe.run()
    assert json.loads((tmp_path / "run/execution.json").read_text())["status"] == "execution_failed"
    with pytest.raises(ValueError):
        bs.open_run(tmp_path / "run")


def test_async_results_are_retained_by_same_engine(tmp_path):
    async def runtime(x):
        return x * 2
    pipe = bs.pipeline("evaluate", system=bs.System.from_callable(
        runtime, name="agents", revision="r1"), benchmark=recipe(),
        config=bs.EvaluationConfig(concurrency=2, output_dir=tmp_path / "run"))
    result = asyncio.run(pipe.arun())
    assert bs.open_run(tmp_path / "run").trials == result.trials


def test_named_backend_errors_are_actionable(monkeypatch, tmp_path):
    monkeypatch.setattr(backend_loading.metadata, "entry_points", lambda **kw: [])
    assert main(["--system", "missing", "--system-revision", "r1", "--benchmark", "missing",
                 "--benchmark-revision", "r1", "--check"]) == 1
    monkeypatch.setattr(backend_loading.metadata, "entry_points", lambda **kw: [
        SimpleNamespace(load=lambda: lambda **kw: None)])
    with pytest.raises(TypeError, match="bs.System"):
        bs.System.from_backend("bad")
    assert not hasattr(bs.Benchmark, "from_pretrained")


def test_duplicate_backend_is_rejected_before_factory_execution(monkeypatch):
    monkeypatch.setattr(backend_loading.metadata, "entry_points", lambda **kw: [object(), object()])
    with pytest.raises(ValueError, match="found 2"):
        bs.System.from_backend("ambiguous")


def test_real_installed_entry_point_discovery_through_cli(tmp_path):
    import os
    import subprocess
    import sys
    site = tmp_path / "installed"
    site.mkdir()
    (site / "synthetic_bs_backend.py").write_text('''import benchstudio as bs

def system(revision):
    return bs.System.from_callable(lambda x: x * 2, name="composed", revision=revision)

def benchmark(revision):
    return bs.Benchmark("tiny", revision, [1, 2], [2, 4],
        lambda output, target: bs.Score(output == target), "exact-r1")
''')
    info = site / "synthetic_bs_backend-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: synthetic-bs-backend\nVersion: 1.0\n")
    (info / "entry_points.txt").write_text(
        "[benchstudio.systems]\nsynthetic = synthetic_bs_backend:system\n"
        "[benchstudio.benchmarks]\nsynthetic = synthetic_bs_backend:benchmark\n")
    output = tmp_path / "retained"
    command = [sys.executable, "-m", "benchstudio", "evaluate", "--system", "synthetic",
               "--system-revision", "system-r1", "--benchmark", "synthetic",
               "--benchmark-revision", "data-r1", "--output", str(output)]
    env = {**os.environ, "PYTHONPATH": str(site) + os.pathsep + os.environ["PYTHONPATH"]}
    checked = subprocess.run(command + ["--check"], env=env, capture_output=True, text=True, timeout=20)
    assert checked.returncode == 0, checked.stderr
    assert not output.exists()
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "2/2 completed" in result.stdout
    assert all(t.success for t in bs.open_run(output).trials)


def test_async_scorer_refused_before_runtime_call():
    calls = []
    async def score(output, target):
        return bs.Score(True)
    data = bs.Benchmark("t", "r", [1], [1], score, "r")
    pipe = bs.pipeline("evaluate", system=bs.System.from_callable(
        lambda x: calls.append(x), name="t", revision="r"), benchmark=data)
    assert not pipe.check().configuration_valid
    with pytest.raises(TypeError, match="async scorers"):
        pipe.run()
    assert not calls


def test_exact_dependency_version_mismatch_and_blocking_async_backend(monkeypatch):
    class Runtime:
        requirements = {"synthetic-backend": "2"}
        supports_async = False
        def __call__(self, x):
            pytest.fail("runtime executed")
    monkeypatch.setattr(backend_loading.metadata, "version", lambda name: "1")
    pipe = bs.pipeline("evaluate", system=bs.System.from_callable(
        Runtime(), name="t", revision="r"), benchmark=recipe())
    assert any("installed 1, required 2" in item for item in pipe.check().issues)
    assert any("synchronous" in item for item in pipe.check(mode="async").issues)
    with pytest.raises(ValueError):
        asyncio.run(pipe.arun())


def test_factory_cannot_silently_change_requested_revision(monkeypatch):
    install(monkeypatch, lambda revision: bs.System.from_callable(lambda x: x, name="t", revision="other"))
    with pytest.raises(ValueError, match="different revision"):
        bs.System.from_backend("demo", revision="r1")


def test_in_memory_result_can_be_saved_without_rerunning(tmp_path):
    calls = []
    pipe = bs.pipeline("evaluate", system=bs.System.from_callable(
        lambda x: calls.append(x) or x * 2, name="t", revision="r"), benchmark=recipe())
    result = pipe.run()
    result.save(tmp_path / "saved")
    assert bs.open_run(tmp_path / "saved").trials == result.trials
    with pytest.raises(FileExistsError):
        result.save(tmp_path / "saved")
    assert calls == [1, 2]
