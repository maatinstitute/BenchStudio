import tempfile
from pathlib import Path

import numpy as np
import pytest

from ival.integrations import (
    checked_rotation_delta,
    compact_record,
    persist,
    replay_equal,
    termination,
)


def test_persistence_serializes_numpy_scalars_and_arrays_without_object_arrays():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "results"
        root.mkdir()
        persist(root / "record.json", {"success": np.bool_(False), "steps": np.int64(2)})
        assert "false" in (root / "record.json").read_text()
        persist(root / "trace.npz", {"actions": np.zeros((0, 7))}, array=True)
        with np.load(root / "trace.npz", allow_pickle=False) as archive:
            assert archive["actions"].shape == (0, 7)


def test_termination_preserves_success_availability_and_fixed_duration_rules():
    def sample(available, success):
        return {"native_success_available": available, "native_success": success}

    assert termination(sample(False, False), False, 0, 156) == "native_success_unavailable"
    assert termination(sample(True, True), False, 1, 156) == "native_success"
    assert termination(sample(True, False), False, 156, 156) == "fixed_duration_exhausted"
    assert termination(sample(True, False), False, 20, 156) is None


def test_replay_equality_requires_exact_trace_frames_contacts_and_no_errors():
    first = {"termination": "fixed_duration_exhausted", "trace": {"states": np.array([1.0])}}
    assert replay_equal(first, first)
    assert not replay_equal(first, {**first, "trace": {"states": np.array([1.00001])}})
    assert not replay_equal(first, {**first, "error": "failed"})
    evidence = {
        "termination": "native_success",
        "trace": {},
        "frame_hashes": ["a"],
        "contacts": [[]],
    }
    assert not replay_equal(evidence, {**evidence, "frame_hashes": ["b"]})
    assert not replay_equal(evidence, {**evidence, "contacts": [[{"distance": 1}]]})


def test_stale_goal_rotation_and_compact_records_are_defensive():
    with pytest.raises(ValueError, match="stale"):
        checked_rotation_delta(np.eye(3), np.eye(3), np.diag([-1, -1, 1]))
    np.testing.assert_array_equal(
        checked_rotation_delta(np.eye(3), np.eye(3), np.eye(3)), np.zeros(3)
    )
    compact = compact_record(
        {
            "id": "H",
            "error": "failure",
            "physics_contacts": [[]] * 1000,
            "detail_record_sha256": "abc",
        }
    )
    assert "physics_contacts" not in compact
    assert compact["error"] == "failure"
