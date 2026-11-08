import json
import pytest
import benchstudio as bs
from benchstudio.system_ablations import audit_ablation
from benchstudio.system_comparison import compare_system_runs
from benchstudio.system_evidence import SystemRun, Trial, TrialKey
from benchstudio.system_importers import import_inspect_robots
from benchstudio.system_spec import Component, SystemSpec
from benchstudio.system_trace import audit_system_trace


def spec(revision="r1"):
    return SystemSpec("composite", revision, (
        Component("world", "world_model", "latent-wm", revision),
        Component("agent", "agent", "planner", "stable"),
    ))


def write_log(tmp_path, *, score=.75):
    doc = {
        "version": 3,
        "status": "success",
        "eval": {"task": "cubepick", "grader": "operator",
                 "environment_revision": "rig-v1"},
        "samples": [{"scene_id": "scene0", "status": "success",
                     "epochs": [{"progress": score}],
                     "record_ids": ["rec-1"]}],
    }
    p = tmp_path / "inspect-log.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def import_run(path, system, **override):
    kwargs = dict(
        system=system, task_revision="v1", protocol_digest="a"*64,
        evaluator_revision="v3", environment_revision="rig-v1",
        seed_by_scene={"scene0": 42}, condition="nominal",
        score_key="progress", trust_grader=True,
    )
    kwargs.update(override)
    return import_inspect_robots(path, **kwargs)


def test_public_api_compares_composed_world_model_systems():
    a, b = spec(), spec("r2")
    assert audit_ablation(a, b, allowed_components=("world",)).structurally_isolated
    assert audit_system_trace(a, []).unobserved_connections == ()
    k = TrialKey("task", "v1", "scene", "nominal", 42, 0,
                    "rig-v1", "a"*64, "grader", "v3")
    ar = SystemRun("a", a, (Trial("t1", k, a.digest, "completed", True,
                                      "declared", True),))
    br = SystemRun("b", b, (Trial("t1", k, b.digest, "completed", False,
                                      "declared", True),))
    result = compare_system_runs(ar, br)
    assert result.valid_binary_pairs == 1
    assert result.paired_success.success_gap_b_minus_a == -1


def test_import_inspect_robots_continuous_grading_not_binary_success(tmp_path):
    log = write_log(tmp_path)
    run = import_run(log, spec())
    assert run.trials[0].success is None
    assert run.trials[0].metrics["progress"] == .75
    assert run.trials[0].valid_success is False
    assert "inspect_robots_eval_log" in run.source_digests


def test_import_inspect_robots_binary_outcome_requires_declared_trust(tmp_path):
    log = write_log(tmp_path, score=1)
    run = import_run(log, spec(), trust_grader=False)
    assert run.trials[0].success is True
    assert not run.trials[0].valid_success
    trusted = import_run(log, spec())
    assert trusted.trials[0].valid_success


def test_import_inspect_robots_rejects_missing_pairing_and_mismatch(tmp_path):
    log = write_log(tmp_path, score=0)
    with pytest.raises(ValueError, match="scene-to-seed"):
        import_run(log, spec(), seed_by_scene={})
    with pytest.raises(ValueError, match="environment revision"):
        import_run(log, spec(), environment_revision="other")
    with pytest.raises(ValueError, match="version 3"):
        log.write_text(json.dumps({"version": 2}), encoding="utf-8")
        import_run(log, spec())
