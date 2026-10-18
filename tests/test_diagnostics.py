from __future__ import annotations

from benchstudio.analysis import bookmark_critical_events
from benchstudio.campaigns import CounterfactualCell, Intervention, validate_counterfactual_pair
from benchstudio.conformance import audit_deadlines


def test_deadline_audit_distinguishes_misses_and_incomplete_runs():
    audit = audit_deadlines([10.0, 50.0], scheduled_calls=3, deadline_ms=25.0)
    assert audit.valid is False
    assert audit.missed_deadlines == 1
    assert any("incomplete" in issue for issue in audit.issues)


def test_critical_event_bookmarks_preserve_evidence():
    events = [
        {
            "event_type": "action_executed",
            "observation_age_ms": 300,
            "action_submitted_monotonic_ns": 1,
        },
        {
            "event_type": "action_executed",
            "observation_age_ms": 0,
            "action_submitted_monotonic_ns": 1_000_000_001,
            "execution_timestamp_status": "unknown",
        },
    ]
    bookmarks = bookmark_critical_events(events, discontinuity_ms=500)
    assert bookmarks[0].reasons == ("stale_observation",)
    assert set(bookmarks[1].reasons) == {"action_timing_gap", "execution_timestamp_unverified"}
    assert bookmarks[1].evidence["event_type"] == "action_executed"


def test_counterfactual_pair_requires_shared_lineage_and_transition():
    nominal = CounterfactualCell(
        "pair-1", "attempt-n", "attempt-n", Intervention("none", 4, "none", {}), "nominal"
    )
    branch = CounterfactualCell(
        "pair-1",
        "attempt-n",
        "attempt-i",
        Intervention("move", 4, "object_displacement", {"m": 0.1}),
    )
    assert validate_counterfactual_pair(nominal, branch) == []
