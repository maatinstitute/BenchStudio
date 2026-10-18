import cProfile
import io

import numpy as np
import pytest

from benchstudio.analysis.refinement_protocol import (
    ATOL,
    CONDITIONS,
    RTOL,
    array_record,
    batch_one_success,
    compare_arrays,
    development_schedule,
    image_variants,
    json_line,
    keyed_seed,
    observation_field_shas,
    observation_sha,
    parity_report,
    profiler_counts,
    select_schedule,
    sha,
)
from benchstudio.campaigns.refinement_plan import make_plan


def test_schedule_and_noise_identity_are_source_compatible():
    rows = development_schedule()
    assert len(rows) == 4
    assert {(row["h"], row["denoising_steps"]) for row in rows} == CONDITIONS
    identity = rows[0]["episode_identity"]
    assert keyed_seed(identity, 10) == keyed_seed(dict(reversed(list(identity.items()))), 10)
    assert keyed_seed(identity, 10) != keyed_seed(identity, 11)
    assert keyed_seed(identity, 10) != keyed_seed(identity, 10, "warmup")


def test_source_schedule_selection_preserves_balanced_pairs_and_rejects_bad_caps():
    plan = make_plan()
    assert len(select_schedule(plan)) == 320
    for cap in (16, 32, 48, 64, 80):
        rows = select_schedule(plan, cap)
        assert len(rows) == cap * 4
        by_task = {}
        for row in rows:
            identity = row["episode_identity"]
            task = (identity["suite"], identity["task_id"])
            by_task.setdefault(task, set()).add(
                (identity["initial_state_id"], identity["policy_seed"])
            )
        assert len(by_task) == 8
        assert all(len(identities) == cap // 8 for identities in by_task.values())
        for identities in by_task.values():
            for state in {state for state, _seed in identities}:
                assert {seed for other, seed in identities if other == state} == {2000, 2001}
    for cap in (-1, 0, 1, 8, 17, 81, True):
        with pytest.raises(ValueError):
            select_schedule(plan, cap)


def test_source_schedule_selection_rejects_digest_and_block_corruption():
    plan = make_plan()
    plan["schedule"][0]["h"] = 99
    with pytest.raises(ValueError, match="digest"):
        select_schedule(plan)
    plan = make_plan()
    plan["schedule"][3], plan["schedule"][4] = plan["schedule"][4], plan["schedule"][3]
    plan["scheduling"]["schedule_sha256"] = sha(plan["schedule"])
    with pytest.raises(ValueError, match="contiguous"):
        select_schedule(plan)


def test_source_development_array_gate_reports_exact_and_tolerant_differences():
    reference = np.zeros((1, 2), dtype=np.float32)
    candidate = reference.copy()
    candidate[0, 1] = 0.001
    report = compare_arrays(reference, candidate)
    assert report["exact_equal"] is False
    assert report["allclose"] is False
    assert report["rtol"] == RTOL
    assert report["atol"] == ATOL
    with pytest.raises(ValueError, match="finite arrays"):
        compare_arrays(reference, reference + np.nan)


def test_source_development_image_variants_preserve_state_and_reject_identical_cameras():
    observation = {
        "pixels": {
            "left": np.ones((1, 3, 3, 3), dtype=np.uint8),
            "wrist": np.full((1, 3, 3, 3), 7, dtype=np.uint8),
        },
        "robot_state": {"position": [1.0, 2.0, 3.0]},
    }
    variants, keys = image_variants(observation)
    assert keys == ["left", "wrist"]
    assert np.all(variants["camera_swap"]["pixels"]["left"] == 7)
    assert np.all(variants["zero_images"]["pixels"]["wrist"] == 0)
    assert variants["native"]["robot_state"] == observation["robot_state"]
    observation["pixels"]["wrist"][:] = 1
    with pytest.raises(ValueError, match="identical"):
        image_variants(observation)


def test_source_profiler_counts_bind_code_identity():
    class First:
        def sample_actions(self):
            return None

    class Second:
        def sample_actions(self):
            return None

    first, second = First(), Second()
    profiler = cProfile.Profile()
    profiler.enable()
    first.sample_actions()
    for _ in range(3):
        second.sample_actions()
    profiler.disable()
    counts = profiler_counts(
        profiler, {"first": first.sample_actions, "second": second.sample_actions}
    )
    assert counts["first"]["total_calls"] == 1
    assert counts["second"]["total_calls"] == 3


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
