from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScheduledAction:
    action_id: str
    command_time_ns: int
    effective_time_ns: int
    action: Any


def apply_zero_order_hold(
    actions: list[ScheduledAction], query_times_ns: list[int]
) -> list[ScheduledAction | None]:
    """Resolve the latest effective command without reusing a future action."""
    ordered = sorted(actions, key=lambda item: (item.effective_time_ns, item.action_id))
    result: list[ScheduledAction | None] = []
    for query in query_times_ns:
        available = [item for item in ordered if item.effective_time_ns <= query]
        result.append(available[-1] if available else None)
    return result


def validate_action_timing(action: ScheduledAction) -> list[str]:
    issues: list[str] = []
    if action.command_time_ns < 0 or action.effective_time_ns < 0:
        issues.append("action timestamps must be non-negative")
    if action.effective_time_ns < action.command_time_ns:
        issues.append("effective_time_ns precedes command_time_ns")
    return issues
