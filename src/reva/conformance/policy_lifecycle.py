from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LifecycleState(str, Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class LifecycleTracker:
    state: LifecycleState = LifecycleState.CREATED

    def transition(self, target: LifecycleState) -> None:
        allowed = {
            LifecycleState.CREATED: {LifecycleState.INITIALIZED, LifecycleState.FAILED},
            LifecycleState.INITIALIZED: {
                LifecycleState.RUNNING,
                LifecycleState.STOPPED,
                LifecycleState.FAILED,
            },
            LifecycleState.RUNNING: {LifecycleState.STOPPED, LifecycleState.FAILED},
            LifecycleState.STOPPED: set(),
            LifecycleState.FAILED: {LifecycleState.STOPPED},
        }
        if target not in allowed[self.state]:
            raise ValueError(f"invalid lifecycle transition: {self.state} -> {target}")
        self.state = target


def validate_lifecycle_events(events: list[dict[str, str]]) -> list[str]:
    tracker = LifecycleTracker()
    issues: list[str] = []
    for index, event in enumerate(events):
        try:
            tracker.transition(LifecycleState(event["state"]))
        except (KeyError, ValueError) as exc:
            issues.append(f"event {index}: {exc}")
    return issues
