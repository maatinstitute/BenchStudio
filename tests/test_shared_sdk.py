from __future__ import annotations

import pytest

from benchstudio.analysis import audit_score_coverage, missing_outcome_bounds
from benchstudio.conformance import (
    LifecycleState,
    LifecycleTracker,
    MappingRule,
    ScheduledAction,
    SignalSpec,
    apply_zero_order_hold,
    validate_action_timing,
    validate_lifecycle_events,
    validate_mapping,
)


def test_lifecycle_rejects_out_of_order_service_events():
    assert validate_lifecycle_events([{"state": "running"}])
    tracker = LifecycleTracker()
    tracker.transition(LifecycleState.INITIALIZED)
    tracker.transition(LifecycleState.RUNNING)
    assert tracker.state == LifecycleState.RUNNING


def test_zero_order_hold_never_uses_a_future_action():
    actions = [
        ScheduledAction("a", 0, 10, "first"),
        ScheduledAction("b", 20, 30, "second"),
    ]
    resolved = apply_zero_order_hold(actions, [0, 10, 25, 30])
    assert [item.action if item else None for item in resolved] == [
        None,
        "first",
        "first",
        "second",
    ]
    assert validate_action_timing(ScheduledAction("bad", 5, 4, "x"))


def test_embodiment_mapping_requires_complete_semantics():
    source = SignalSpec("source", "joint_position", "rad", ("j1", "j2"), "base")
    target = SignalSpec("target", "joint_position", "rad", ("left", "right"), "base")
    rules = (MappingRule("j1", "left"), MappingRule("j2", "right", invert=True))
    assert validate_mapping(source, target, rules) == []
    assert MappingRule("j1", "left", scale=2).apply(0.5) == 1.0


def test_score_coverage_and_missing_outcome_bounds_are_explicit():
    coverage = audit_score_coverage(
        scheduled_steps=10, observed_steps=8, scored_steps=8, success_step=5
    )
    assert coverage.complete is False
    assert coverage.post_success_steps == 2
    assert "score does not cover" in coverage.issues[0]
    bounds = missing_outcome_bounds(scheduled=10, observed=8, successes=4)
    assert bounds.lower_success_rate == 0.4
    assert bounds.upper_success_rate == 0.6
    with pytest.raises(ValueError):
        missing_outcome_bounds(scheduled=2, observed=3, successes=1)
