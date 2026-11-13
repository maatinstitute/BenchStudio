from __future__ import annotations

import pytest

from ival.analysis import (
    summarize_selective_responsiveness,
)


def row(i=0, relevant=True, **kwargs):
    value = dict(
        pair_id=f"p{i}",
        episode_id=f"e{i}",
        split="test",
        oracle_status="validated",
        oracle_evidence="fixture",
        should_change=relevant,
        appropriate_change=True,
        stable=True,
        correct_0=True,
        correct_1=True,
    )
    value.update(kwargs)
    return value


def test_perfect_and_correctness_are_distinct():
    assert summarize_selective_responsiveness([row(), row(1, False)], draws=20)["scr"] == 1.0
    changed = row()
    changed["correct_1"] = False
    assert summarize_selective_responsiveness([changed, row(1, False)], draws=20)["scr"] == 0.0


def test_missing_class_is_undefined_and_validation_is_fail_closed():
    assert summarize_selective_responsiveness([row()])["scr"] is None
    invalid = row()
    invalid["should_change"] = None
    with pytest.raises(ValueError):
        summarize_selective_responsiveness([invalid])


def test_episode_leakage_and_duplicate_pairs_are_rejected():
    leaked = row(1, episode_id="e0", split="train")
    with pytest.raises(ValueError):
        summarize_selective_responsiveness([row(), leaked])
    with pytest.raises(ValueError):
        summarize_selective_responsiveness([row(), row()])
