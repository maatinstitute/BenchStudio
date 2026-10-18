from __future__ import annotations

from benchstudio.integrations import (
    LogicalReplayClock,
    ReplayTimingRecording,
    ReplayTimingSample,
    build_replay_schedule,
    replay_schedule_duration_ms,
    resolve_command_time_ms,
)


def recording():
    return ReplayTimingRecording(
        started_at_ms=1_000,
        ended_at_ms=2_000,
        samples=(
            ReplayTimingSample(0, recorded_at_ms=1_050, source_ts_ms=1_100),
            ReplayTimingSample(1, recorded_at_ms=1_300, source_ts_ms=900),
            ReplayTimingSample(2, recorded_at_ms=2_100, source_ts_ms=2_100),
        ),
    )


def test_source_timestamp_precedence_and_fallback():
    value = recording()
    assert resolve_command_time_ms(value, value.samples[0]) == 100.0
    assert resolve_command_time_ms(value, value.samples[1]) == 300.0
    assert resolve_command_time_ms(value, value.samples[2]) == 1_100.0


def test_schedule_is_monotonic_and_duration_is_last_effective_time():
    schedule = build_replay_schedule(recording())
    assert [entry.scheduled_time_ms for entry in schedule] == [100.0, 300.0, 1_100.0]
    assert [entry.scheduled_delay_ms for entry in schedule] == [100.0, 200.0, 800.0]
    assert replay_schedule_duration_ms(schedule) == 1_100.0


def test_logical_clock_never_waits_backward():
    clock = LogicalReplayClock()
    assert clock.wait_until_ms(100.0) == 100.0
    assert clock.wait_until_ms(50.0) == 0.0
    assert clock.current_time_ms == 100.0
