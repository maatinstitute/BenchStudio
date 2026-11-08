import json
from types import SimpleNamespace
from unittest.mock import patch

import benchstudio as bs


def benchmark():
    return bs.Benchmark("task", "r1", [1], [2], lambda x, y: bs.Score(x == y), "score-r1")


def test_default_pipeline_and_evaluate_alias_preserve_same_result():
    system = bs.System.from_callable(lambda x: x * 2, name="system", revision="r1")
    data = benchmark()
    runs = [bs.pipeline(**kwargs, system=system, benchmark=data).run()
            for kwargs in ({}, {"name": "evaluate"}, {"name": "system-evaluation"})]
    assert all(run.trials == runs[0].trials for run in runs)


def test_benchmark_load_and_compatibility_alias_use_same_installed_recipe(monkeypatch):
    monkeypatch.setattr("benchstudio.backend_loading.metadata.entry_points", lambda **kw: [
        SimpleNamespace(load=lambda: lambda revision: benchmark())])
    a = bs.Benchmark.load("installed", revision="r1")
    b = bs.Benchmark.from_pretrained("installed", revision="r1")
    assert a.protocol_digest == b.protocol_digest


def test_refinement_workspace_uses_existing_canonical_layout_by_default(tmp_path):
    helper = tmp_path / "experiments/tooling/cross_policy_v3/prepare_campaign.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("")
    report = {"schema": "refinement_campaign_preparation_v1", "model": "pi05",
              "read_only": True, "issues": [], "execution_authorized": False, "commands": {}}
    with patch("benchstudio.refinement.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout=json.dumps(report), stderr="")) as run:
        bs.RefinementWorkspace(tmp_path).prepare(model="pi05")
    argv = run.call_args.args[0]
    assert argv[argv.index("--workspace") + 1] == str(
        tmp_path / "experiments/runs/cross_policy_confirmation_v2")
    assert len(argv) == 6
