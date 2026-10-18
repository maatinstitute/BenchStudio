import json
from pathlib import Path

import numpy as np
import pytest

from benchstudio.campaigns.robopad_assay_plan import (
    CONSUMED,
    all_slots,
    load_reference_attempt,
    remaining_slots,
    sha,
    suffix_seed,
)
from benchstudio.integrations.robopad_reference_cache import select_prefix


def test_slots_and_noise():
    assert len(set(all_slots())) == 360
    assert len(set(remaining_slots())) == 353
    assert not (set(remaining_slots()) & CONSUMED)
    seeds = [
        suffix_seed(task, demo, step)
        for task in range(3)
        for demo in range(2)
        for step in range(201)
    ]
    assert len(set(seeds)) == 1206
    assert suffix_seed(0, 0, 17) == 7_140_017
    with pytest.raises(ValueError):
        suffix_seed(0, 0, 201)
    with pytest.raises(ValueError):
        suffix_seed(False, 0, 1)


def _fixture(root: Path):
    case = root / "D_attempt"
    case.mkdir()
    source = root / "source.json"
    source.write_text(json.dumps({"task_id": "libero_object/0/task", "demo_id": "demo_0"}))
    action = np.zeros((20, 7))
    np.savez(
        case / "trace.npz",
        executed_actions=action,
        commanded_actions=action,
        original_states=np.zeros((21, 10)),
        original_native_success_available=np.ones(21, dtype=bool),
        original_native_success=np.zeros(21, dtype=bool),
    )
    row = {
        "id": "D_attempt",
        "termination": "environment_done_without_success",
        "executed_actions": 20,
        "commanded_actions": 20,
        "trace_sha256": sha(case / "trace.npz"),
    }
    (case / "record.json").write_text(json.dumps(row))
    row["detail_record_sha256"] = sha(case / "record.json")
    report = root / "report.json"
    report.write_text(
        json.dumps(
            {
                "source_pin": {"task": 0, "demo": 0, "sha256": sha(source)},
                "training": False,
                "policy_loaded": False,
                "rows": [row],
            }
        )
    )
    return case, {
        "source_manifest": source,
        "source_manifest_sha256": sha(source),
        "report_path": report,
        "report_sha256": sha(report),
        "task": 0,
        "demo": 0,
        "world": "D",
    }


def test_unsuccessful_attempt_retained(tmp_path):
    case, arguments = _fixture(tmp_path)
    cache = load_reference_attempt(case, **arguments)
    assert cache.prefix(20).shape == (20, 7)
    with pytest.raises(ValueError):
        select_prefix({"D": cache}, "D", 5, insensitive=True)


def test_provenance_and_replay_rejected(tmp_path):
    case, arguments = _fixture(tmp_path)
    with pytest.raises(ValueError):
        load_reference_attempt(case.parent / "D_replay", **arguments)
    with pytest.raises(ValueError):
        load_reference_attempt(case, **{**arguments, "source_manifest_sha256": "0" * 64})
    with pytest.raises(ValueError):
        load_reference_attempt(case, **{**arguments, "demo": 1})
    (case / "trace.npz").write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        load_reference_attempt(case, **arguments)


def test_cache_preserves_held_source_and_rejects_short_or_mutable_inputs():
    from benchstudio.integrations.robopad_reference_cache import cache_executed_source

    caches = {
        source: cache_executed_source(source, np.full((20, 7), value), "a" * 64)
        for source, value in (("H", 0.2), ("D", -0.3), ("I", 0.4))
    }
    for source in caches:
        np.testing.assert_array_equal(
            select_prefix(caches, source, 5, insensitive=True), np.full((5, 7), 0.2)
        )
    actions = np.zeros((20, 7))
    cache = cache_executed_source("H", actions, "a" * 64)
    actions[:] = 1
    retrieved = cache.prefix(20)
    retrieved[:] = 1
    np.testing.assert_array_equal(cache.prefix(20), np.zeros((20, 7)))
    short = cache_executed_source("D", np.zeros((4, 7)), "a" * 64)
    with pytest.raises(ValueError):
        short.prefix(5)
    with pytest.raises(ValueError):
        cache_executed_source("H", np.ones((20, 7)) * 2, "a" * 64)
