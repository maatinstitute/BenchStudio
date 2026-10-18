from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventBookmark:
    event_index: int
    event_type: str
    reasons: tuple[str, ...]
    evidence: dict[str, Any]


def bookmark_critical_events(
    events: list[dict[str, Any]], *, stale_age_ms: float = 250.0, discontinuity_ms: float = 500.0
) -> list[EventBookmark]:
    """Create explainable bookmarks; absent signals do not become failures."""
    bookmarks: list[EventBookmark] = []
    previous_action_ns: int | None = None
    for index, event in enumerate(events):
        reasons: list[str] = []
        age = event.get("observation_age_ms")
        if isinstance(age, (int, float)) and age > stale_age_ms:
            reasons.append("stale_observation")
        timestamp = event.get("action_submitted_monotonic_ns")
        if isinstance(timestamp, int) and previous_action_ns is not None:
            if (timestamp - previous_action_ns) / 1_000_000 > discontinuity_ms:
                reasons.append("action_timing_gap")
        if isinstance(timestamp, int):
            previous_action_ns = timestamp
        if event.get("execution_timestamp_status") not in (None, "simulator_step_returned"):
            reasons.append("execution_timestamp_unverified")
        if reasons:
            bookmarks.append(
                EventBookmark(
                    index,
                    str(event.get("event_type", "unknown")),
                    tuple(reasons),
                    dict(event),
                )
            )
    return bookmarks
