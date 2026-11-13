from __future__ import annotations

from ival.integrations import (
    SyntheticLifecycleService,
    run_synthetic_lifecycle_cycle,
)


def test_duplicate_close_is_idempotent_and_structured():
    service = SyntheticLifecycleService(hardened=True)
    service.start_session("session-a")
    service.close_session("session-a")
    event = service.close_session("session-a")
    evidence = service.evidence()
    assert event.code == "duplicate_close_idempotent"
    assert event.severity == "warning"
    assert evidence["service_survived"] is True
    assert evidence["warning_counts"] == {"duplicate_close_idempotent": 1}


def test_late_messages_do_not_crash_hardened_service():
    service = SyntheticLifecycleService(hardened=True)
    service.start_session("session-a")
    service.close_session("session-a")
    image = service.submit_image_observation("session-a", timestamp_us=2_000)
    route = service.submit_route("session-a", route_waypoints=[{"x": 1.0, "y": 0.0}])
    assert image.code == "late_image_after_close"
    assert route.code == "late_route_after_close"
    assert service.evidence()["service_survived"] is True


def test_sessions_are_isolated_and_strict_mode_is_observable():
    service = SyntheticLifecycleService(hardened=True)
    service.start_session("first")
    service.submit_route("first", [{"x": 1.0, "y": 0.0}])
    service.close_session("first")
    service.start_session("second")
    assert service.evidence()["session_state"]["second"]["route_count"] == 0

    result = run_synthetic_lifecycle_cycle(
        hardened=False,
        schedule=["lifecycle.duplicate_close", "lifecycle.late_image"],
        session_id="strict",
    )
    assert result["service_survived"] is False
    assert result["observed_code"] == "duplicate_close_unhandled"
