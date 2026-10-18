"""Source-backed teleoperation replay timing core.

This is the dependency-free timing portion of ``urdf-ops``' teleop replay
service. Gateway command execution and robot-state validation remain owned by
the source runtime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any, Protocol

MILLISECONDS_PER_SECOND = 1_000.0
TIMING_MODE_LOGICAL = "logical"
TIMING_MODE_WALL_CLOCK = "wall_clock"


@dataclass(frozen=True)
class ReplayTimingSample:
    sample_index: int
    recorded_at_ms: int
    source_ts_ms: int | float


@dataclass(frozen=True)
class ReplayTimingRecording:
    started_at_ms: int
    ended_at_ms: int
    samples: tuple[ReplayTimingSample, ...]


@dataclass(frozen=True)
class ReplayScheduleEntry:
    sample: ReplayTimingSample
    scheduled_time_ms: float
    scheduled_delay_ms: float


class ReplayClock(Protocol):
    timing_mode: str

    def wait_until_ms(self, scheduled_time_ms: float) -> float: ...


class LogicalReplayClock:
    timing_mode = TIMING_MODE_LOGICAL

    def __init__(self) -> None:
        self.current_time_ms = 0.0

    def wait_until_ms(self, scheduled_time_ms: float) -> float:
        wait_ms = max(0.0, scheduled_time_ms - self.current_time_ms)
        self.current_time_ms = max(self.current_time_ms, scheduled_time_ms)
        return wait_ms


class WallClockReplayClock:
    timing_mode = TIMING_MODE_WALL_CLOCK

    def __init__(self) -> None:
        self.started_at_seconds = monotonic()

    def wait_until_ms(self, scheduled_time_ms: float) -> float:
        elapsed_ms = (monotonic() - self.started_at_seconds) * MILLISECONDS_PER_SECOND
        wait_ms = max(0.0, scheduled_time_ms - elapsed_ms)
        if wait_ms > 0.0:
            sleep(wait_ms / MILLISECONDS_PER_SECOND)
        return wait_ms


def resolve_command_time_ms(recording: ReplayTimingRecording, sample: ReplayTimingSample) -> float:
    """Use episode-local source time when valid, otherwise recorded time."""
    for absolute_timestamp_ms in (sample.source_ts_ms, sample.recorded_at_ms):
        if _is_episode_timestamp(recording, absolute_timestamp_ms):
            return max(0.0, float(absolute_timestamp_ms - recording.started_at_ms))
    return max(0.0, float(sample.recorded_at_ms - recording.started_at_ms))


def build_replay_schedule(
    recording: ReplayTimingRecording,
) -> list[ReplayScheduleEntry]:
    schedule: list[ReplayScheduleEntry] = []
    previous_time_ms = 0.0
    for sample in recording.samples:
        scheduled_time_ms = resolve_command_time_ms(recording, sample)
        scheduled_delay_ms = max(0.0, scheduled_time_ms - previous_time_ms)
        schedule.append(ReplayScheduleEntry(sample, scheduled_time_ms, scheduled_delay_ms))
        previous_time_ms = max(previous_time_ms, scheduled_time_ms)
    return schedule


def replay_schedule_duration_ms(schedule: list[ReplayScheduleEntry]) -> float:
    return max((entry.scheduled_time_ms for entry in schedule), default=0.0)


def _is_episode_timestamp(recording: ReplayTimingRecording, value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return recording.started_at_ms <= value <= recording.ended_at_ms
    return (
        isinstance(value, float)
        and math.isfinite(value)
        and recording.started_at_ms <= value <= recording.ended_at_ms
    )
