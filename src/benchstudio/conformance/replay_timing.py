from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import ClockDomain


@dataclass(frozen=True)
class ScheduledAction:
    action_id: str
    command_time_ns: int
    effective_time_ns: int
    action: Any
    command_clock_domain: ClockDomain = "sim_time"
    effective_clock_domain: ClockDomain = "sim_time"
    queue_sequence: int | None = None
    deadline_ns: int | None = None
    dropped: bool = False
    drop_reason: str | None = None


@dataclass(frozen=True)
class ActionQueueAudit:
    submitted: int
    effective: int
    dropped: int
    issues: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.issues and self.submitted == self.effective + self.dropped


def apply_zero_order_hold(
    actions: list[ScheduledAction], query_times_ns: list[int]
) -> list[ScheduledAction | None]:
    """Resolve the latest effective command without reusing a future action."""
    ordered = sorted(
        (item for item in actions if not item.dropped),
        key=lambda item: (
            item.effective_time_ns,
            item.queue_sequence if item.queue_sequence is not None else float("inf"),
            item.action_id,
        ),
    )
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
    if action.command_clock_domain != action.effective_clock_domain:
        issues.append("command and effective timestamps use different clock domains")
    if action.queue_sequence is not None and action.queue_sequence < 0:
        issues.append("queue_sequence must be non-negative")
    if action.deadline_ns is not None and action.command_time_ns > action.deadline_ns:
        issues.append("command_time_ns is after controller deadline")
    if action.dropped and not action.drop_reason:
        issues.append("dropped actions require drop_reason")
    return issues


def audit_action_queue(actions: list[ScheduledAction]) -> ActionQueueAudit:
    """Audit queue accounting without treating dropped commands as executed."""
    issues: list[str] = []
    sequences = [item.queue_sequence for item in actions if item.queue_sequence is not None]
    if len(sequences) != len(set(sequences)):
        issues.append("queue_sequence values must be unique")
    domains = {
        domain
        for item in actions
        for domain in (item.command_clock_domain, item.effective_clock_domain)
    }
    if len(domains) > 1:
        issues.append("action queue mixes clock domains")
    for item in actions:
        issues.extend(f"{item.action_id}: {issue}" for issue in validate_action_timing(item))
    dropped = sum(item.dropped for item in actions)
    return ActionQueueAudit(
        submitted=len(actions),
        effective=len(actions) - dropped,
        dropped=dropped,
        issues=tuple(issues),
    )
