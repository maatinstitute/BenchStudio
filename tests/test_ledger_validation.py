from __future__ import annotations

import copy
import hashlib
import json

import numpy as np
import pytest

from benchstudio.analysis import compare_refinement_ledgers, validate_refinement_ledger


def array_record(value):
    array = np.asarray(value, dtype=np.float32)
    header = json.dumps([array.dtype.str, list(array.shape)], separators=(",", ":"))
    return {
        "values": array.tolist(),
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "sha256": hashlib.sha256(
            header.encode() + np.ascontiguousarray(array).tobytes()
        ).hexdigest(),
    }


def fixture():
    action = array_record([[0.1, 0.2]])
    episode = {
        "identity": ["spatial", 0, 0, 42],
        "seeds": {key: 42 for key in ("python", "numpy", "torch", "libero")},
        "initial_state": array_record([1.0, 2.0]),
        "select_calls": 2,
        "complete": True,
        "max_steps": 5,
        "success": True,
        "producer_steps": [{"step": index, "action": copy.deepcopy(action)} for index in range(2)],
    }
    episode["environment_steps"] = copy.deepcopy(episode["producer_steps"])
    for index, row in enumerate(episode["environment_steps"]):
        row.update(
            reward=float(index), terminated=bool(index), truncated=False, success=bool(index)
        )
    return {
        "schema_version": 3,
        "complete": True,
        "contract": {
            "config": {"policy": {}},
            "checkpoint": {"weights": "test"},
            "software": {"torch": "test"},
            "source": {"ledger": "test"},
        },
        "h": 1,
        "denoising_steps": 10,
        "warmup_passes": 1,
        "episodes": [episode],
        "chunk_calls": {"warmup": 1, "measured": 2},
        "sampler_calls": {"warmup": 1, "measured": 2},
        "inferences": [
            {"phase": phase, "episode": episode["identity"], "step": step, "cuda_ms": 1.0}
            for phase, step in [("warmup", 0), ("measured", 0), ("measured", 1)]
        ],
    }


def test_valid_pairing_and_replay():
    validate_refinement_ledger(fixture())
    compare_refinement_ledgers(fixture(), fixture(), replay=True)


def test_pairing_allows_behavior_difference_but_replay_rejects_it():
    changed = fixture()
    changed["episodes"][0]["environment_steps"][0]["action"] = array_record([[8.0, 9.0]])
    changed["episodes"][0]["producer_steps"][0]["action"] = array_record([[8.0, 9.0]])
    compare_refinement_ledgers(fixture(), changed)
    with pytest.raises(ValueError, match="action replay"):
        compare_refinement_ledgers(fixture(), changed, replay=True)


def test_pairing_rejects_initial_state_and_contract_mismatch():
    changed = fixture()
    changed["episodes"][0]["initial_state"] = array_record([3.0, 4.0])
    with pytest.raises(ValueError, match="initial states"):
        compare_refinement_ledgers(fixture(), changed)
    changed = fixture()
    changed["contract"]["checkpoint"]["weights"] = "different"
    with pytest.raises(ValueError, match="contracts"):
        compare_refinement_ledgers(fixture(), changed, replay=True)


def test_faults_fail_closed():
    faults = [
        lambda data: data["episodes"][0]["environment_steps"].pop(),
        lambda data: data["sampler_calls"].update(measured=3),
        lambda data: data["inferences"][1].update(step=9),
        lambda data: data["inferences"][1].update(cuda_ms=float("nan")),
        lambda data: data.update(warmup_passes=0),
        lambda data: data.update(h=True),
        lambda data: data["episodes"][0].update(success=False),
    ]
    for fault in faults:
        data = fixture()
        fault(data)
        with pytest.raises(ValueError):
            validate_refinement_ledger(data)
