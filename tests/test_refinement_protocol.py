import io

import numpy as np
import pytest

from benchstudio.analysis.refinement_protocol import (
    CONDITIONS,
    array_record,
    batch_one_success,
    development_schedule,
    json_line,
    keyed_seed,
    observation_field_shas,
    observation_sha,
    parity_report,
    sha,
)


def test_schedule_and_noise_identity_are_source_compatible():
    rows = development_schedule()
    assert len(rows) == 4
    assert {(row["h"], row["denoising_steps"]) for row in rows} == CONDITIONS
    identity = rows[0]["episode_identity"]
    assert keyed_seed(identity, 10) == keyed_seed(dict(reversed(list(identity.items()))), 10)
    assert keyed_seed(identity, 10) != keyed_seed(identity, 11)
    assert keyed_seed(identity, 10) != keyed_seed(identity, 10, "warmup")


def test_array_and_nested_observation_hashes_bind_shape_dtype_and_fields():
    record = array_record(np.array([1.0, 2.0], dtype=np.float32))
    assert record == array_record(np.array([1.0, 2.0], dtype=np.float32))
    assert record["sha256"] != array_record(np.array([[1.0, 2.0]], dtype=np.float32))["sha256"]
    assert record["sha256"] != array_record(np.array([1.0, 2.0], dtype=np.float64))["sha256"]
    with pytest.raises(ValueError, match="nonfinite"):
        array_record([float("nan")])
    observation = {
        "image": np.array([[1, 2]], dtype=np.uint8),
        "state": {"q": np.array([0.5], dtype=np.float32)},
    }
    fields = observation_field_shas(observation)
    assert set(fields) == {"image", "state"}
    assert set(fields["state"]) == {"q"}
    assert len(fields["image"]) == 64
    assert len(observation_sha(observation)) == 64


def test_batch_success_and_journal_contract_fail_closed():
    assert batch_one_success({"is_success": [True]}) is True
    assert batch_one_success({"final_info": [{"is_success": True}]}) is True
    with pytest.raises(ValueError, match="missing"):
        batch_one_success({})
    with pytest.raises(ValueError, match="batch one"):
        batch_one_success({"is_success": [True, False]})
    stream = io.StringIO()
    json_line(stream, {"kind": "step", "value": 1})
    assert stream.getvalue().count("\n") == 1
    with pytest.raises(ValueError):
        json_line(stream, {"value": float("nan")})


def test_parity_report_detects_late_action_changes():
    actions = np.array([[1, 2], [3, 4]], dtype=np.float32)
    initial = array_record(np.array([0.1, 0.2], dtype=np.float64))
    reference = {
        "run_id": "synthetic",
        "episode_identity": {},
        "h": 1,
        "denoising_steps": 10,
        "initial_state": initial,
        "initial_observation_sha256": "obs",
        "steps": 2,
        "success": True,
        "action_stream_sha256": sha([array_record(action)["sha256"] for action in actions]),
    }
    assert parity_report(reference, initial, "obs", actions, True)["status"] == "passed"
    altered = actions.copy()
    altered[0, 0] += 1
    assert parity_report(reference, initial, "obs", altered, True)["status"] == "failed"
