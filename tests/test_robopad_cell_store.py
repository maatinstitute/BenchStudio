import numpy as np
import pytest

from benchstudio.integrations.robopad_cell_store import CellStore


def test_aux_semantic_digest_is_independent_of_output_directory(tmp_path):
    digests = []
    for suffix in ("attempt", "replay"):
        store = CellStore(tmp_path / suffix, cell_id=suffix, k=5, byte_cap=100_000, reserve=10_000)
        frames = {
            stream + "_" + str(camera): np.zeros((2, 2, 3), np.uint8)
            for stream in ("original", "physics")
            for camera in range(2)
        }
        store.frame(0, frames)
        store.aux(1, {"state": np.array([1.0, 2.0])}, {"step": 0})
        digests.append(store.finish({"status": "complete"})["semantic_sha256"])
        with pytest.raises(RuntimeError):
            store.aux(2, {"state": np.zeros(1)}, {})
    assert digests[0] == digests[1]


def test_partial_journal_distinguishes_pending_execution(tmp_path):
    store = CellStore(tmp_path / "cell", cell_id="cell", k=1, byte_cap=100_000, reserve=50_000)
    result = {
        "actions": np.empty((0, 7)),
        "reward": np.empty(0),
        "done": np.empty(0, dtype=bool),
        "pending_action": np.ones(7),
        "failure_stage": "environment_step",
    }
    receipt = store.partial_result(result)
    with np.load(store.path / "partial-actions.npz", allow_pickle=False) as arrays:
        assert arrays["actions"].shape == (0, 7)
        np.testing.assert_array_equal(arrays["pending_action_execution_unknown"], np.ones(7))
    assert receipt["pending_execution_unknown"] is True
    assert receipt["failure_stage"] == "environment_step"


def test_partial_journal_retains_executed_actions_after_failure(tmp_path):
    store = CellStore(tmp_path / "cell", cell_id="cell", k=5, byte_cap=100_000, reserve=50_000)
    result = {
        "actions": np.ones((2, 7)),
        "reward": np.zeros(2),
        "done": np.zeros(2, dtype=bool),
        "failure_stage": "post_action_sample",
    }
    receipt = store.partial_result(result)
    with np.load(store.path / "partial-actions.npz", allow_pickle=False) as arrays:
        np.testing.assert_array_equal(arrays["actions"], np.ones((2, 7)))
    assert receipt["actions"] == 2
    assert (store.path / "partial-actions.commit.json").exists()
    store.finish({"status": "failed"})
    with pytest.raises(RuntimeError):
        store.partial_result(result)


def test_aux_object_and_persisted_corruption_fail_closed(tmp_path):
    store = CellStore(tmp_path / "cell", cell_id="cell", k=1, byte_cap=100_000, reserve=10_000)
    with pytest.raises(ValueError):
        store.aux(1, {"bad": np.array([object()])}, {})
    assert store.failed
    assert store.finish({"status": "failed"})["store_failed"] is True
