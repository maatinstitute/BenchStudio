from __future__ import annotations

import pytest

from ival.analysis import audit_score_coverage, missing_outcome_bounds
from ival.conformance import (
    EmbodimentRef,
    LifecycleState,
    LifecycleTracker,
    MappingEndpoint,
    MappingRule,
    MappingSpec,
    RepresentationSignalSpec,
    RepresentationSpec,
    ScheduledAction,
    SignalSpec,
    apply_zero_order_hold,
    validate_action_timing,
    validate_lifecycle_events,
    validate_mapping,
    validate_representation_mapping,
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
    duplicate = (MappingRule("j1", "left"), MappingRule("j1", "right"))
    assert "source labels are duplicated" in validate_mapping(source, target, duplicate)


def test_urdf_ops_style_representation_mapping_is_content_addressed():
    source = EmbodimentRef("source", urdf_sha256="a" * 64)
    target = EmbodimentRef("target", urdf_sha256="b" * 64)
    source_rep = RepresentationSpec(
        "source-joints",
        RepresentationSignalSpec("state", "rad", "source-order", ("j1",)),
        RepresentationSignalSpec(
            "joint_position", "rad", "source-order", ("j1",), base_frame="base"
        ),
    )
    target_rep = RepresentationSpec(
        "target-joints",
        RepresentationSignalSpec("state", "rad", "target-order", ("q1",)),
        RepresentationSignalSpec(
            "joint_position", "rad", "target-order", ("q1",), base_frame="base"
        ),
    )
    mapping = MappingSpec(
        MappingEndpoint("source", "source-joints"),
        MappingEndpoint("target", "target-joints"),
        (MappingRule("j1", "q1", invert=True),),
    )
    assert validate_representation_mapping(source, source_rep, target, target_rep, mapping) == []
    assert len(mapping.content_id()) == 64


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


def test_score_coverage_accepts_declared_early_success_but_not_censoring():
    early_success = audit_score_coverage(
        scheduled_steps=10,
        observed_steps=6,
        scored_steps=6,
        success_step=5,
        termination_reason="success",
    )
    assert early_success.complete is True
    assert early_success.issues == ()

    censored = audit_score_coverage(
        scheduled_steps=10,
        observed_steps=6,
        scored_steps=6,
        termination_reason="censored",
    )
    assert censored.complete is False
    assert censored.issues == ("evaluation is incomplete: censored",)


def test_score_coverage_rejects_invalid_success_identity_and_termination():
    negative = audit_score_coverage(
        scheduled_steps=0,
        observed_steps=0,
        scored_steps=0,
        success_step=-1,
        termination_reason="success",
    )
    assert negative.complete is False
    assert "success_step must be a non-negative integer" in negative.issues
    inconsistent = audit_score_coverage(
        scheduled_steps=2,
        observed_steps=2,
        scored_steps=2,
        success_step=1,
        termination_reason="failure",
    )
    assert "success_step requires success termination" in inconsistent.issues
    invalid = audit_score_coverage(
        scheduled_steps=1,
        observed_steps=1,
        scored_steps=1,
        termination_reason="unknown",  # type: ignore[arg-type]
    )
    assert "termination_reason is invalid" in invalid.issues


def test_score_coverage_rejects_non_integer_counts_without_raising():
    audit = audit_score_coverage(
        scheduled_steps=True,
        observed_steps="2",  # type: ignore[arg-type]
        scored_steps=1,
    )
    assert audit.complete is False
    assert any("non-negative integers" in issue for issue in audit.issues)


def test_score_coverage_rejects_non_string_termination_without_raising():
    audit = audit_score_coverage(
        scheduled_steps=2,
        observed_steps=2,
        scored_steps=2,
        termination_reason=["success"],  # type: ignore[arg-type]
    )
    assert audit.complete is False
    assert "termination_reason is invalid" in audit.issues
