import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import benchstudio as bs
from benchstudio.refinement import RefinementWorkspace

def benchmark():
    return bs.Benchmark("task", "r1", [1], [2], lambda x, y: bs.Score(x == y), "score-r1")

def test_default_pipeline_has_one_canonical_task_name():
    system = bs.System.from_callable(lambda x: x * 2, name="system", revision="r1")
    data = benchmark()
    result = bs.pipeline(system=system, benchmark=data).run()
    assert result.trials[0].success
    with pytest.raises(ValueError, match="unsupported BenchStudio pipeline task"):
        bs.pipeline("system-evaluation", system=system, benchmark=data)

def test_benchmark_load_has_one_canonical_constructor(monkeypatch):
    monkeypatch.setattr("benchstudio.backend_loading.metadata.entry_points", lambda **kw: [
        SimpleNamespace(load=lambda: lambda revision: benchmark())])
    result = bs.Benchmark.load("installed", revision="r1")
    assert result.protocol_digest == benchmark().protocol_digest
    assert not hasattr(bs.Benchmark, "from_pretrained")

def test_refinement_workspace_uses_declared_canonical_layout(tmp_path):
    helper = tmp_path / "experiments/tooling/cross_policy_v3/prepare_campaign.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("")
    report = {"schema": "refinement_campaign_preparation_v1", "model": "pi05",
              "read_only": True, "issues": [], "configuration_valid": False,
              "execution_authorized": False, "commands": {}}
    with patch("benchstudio.refinement.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout=json.dumps(report), stderr="")) as run:
        RefinementWorkspace(tmp_path).prepare(model="pi05")
    argv = run.call_args.args[0]
    assert argv[argv.index("--workspace") + 1] == str(
        tmp_path / "experiments/runs/cross_policy_confirmation_v2")
    assert len(argv) == 6
