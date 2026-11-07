import hashlib
import json
from pathlib import Path
import pytest
from benchstudio.system_spec import Component, SystemSpec
from benchstudio.system_evidence import TrialKey, Trial, SystemRun, open_run


def spec():
    return SystemSpec("robot-system", "r1", (Component("actor", "vla", "smolvla", "v1"),))


def key():
    return TrialKey("pick", "v1", "roomA", "nominal", 7, 0, "mujoco-v1", "a"*64, "task_checker", "r1")


def trial(**kw):
    opts = dict(trial_id="t1", key=key(), system_digest=spec().digest,
                status="completed", success=True, outcome_source="official",
                authoritative=True, metrics={"prediction_error": .3})
    opts.update(kw)
    return Trial(**opts)


def test_run_can_contain_success_and_non_binary_metrics():
    r = SystemRun("r1", spec(), (trial(),))
    assert r.trials[0].valid_success
    assert r.trials[0].metrics["prediction_error"] == .3


def test_missing_or_invalid_result_is_not_success():
    record = trial(status="execution_failed", success=None)
    assert not record.valid_success
    with pytest.raises(ValueError, match="incomplete"):
        trial(status="execution_failed", success=False)
    with pytest.raises(ValueError, match="supplementary"):
        trial(outcome_source="supplementary")


def test_duplicate_key_and_mismatched_graph_rejected():
    with pytest.raises(ValueError, match="duplicate experimental"):
        SystemRun("r", spec(), (trial(), trial(trial_id="other")))
    with pytest.raises(ValueError, match="different system"):
        SystemRun("r", spec(), (trial(system_digest="b"*64),))


def test_offline_bundle_hash_verification(tmp_path):
    system_file = tmp_path / "system.json"
    system_file.write_text(json.dumps(spec().to_dict()), encoding="utf-8")
    trial_file = tmp_path / "trials.jsonl"
    trial_file.write_text(json.dumps(trial().to_dict()) + "\n", encoding="utf-8")
    manifest = {"schema": "benchstudio.system_run.v1", "run_id": "trial-a",
                "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (system_file, trial_file)}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert open_run(tmp_path).trials[0].valid_success
    trial_file.write_text(trial_file.read_text() + "\n")
    with pytest.raises(ValueError, match="digest mismatch"):
        open_run(tmp_path)


def test_empty_and_unscored_are_not_conjured_into_success(tmp_path):
    assert SystemRun("r", spec(), ()).trials == ()
    assert not trial(success=None, authoritative=False).valid_success
