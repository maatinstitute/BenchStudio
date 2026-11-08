"""Execution contract for persistent workers and interactive evaluation cases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass(frozen=True)
class CaseResult:
    """Operational completion and backend-owned output, not task success."""
    completed: bool
    output: Any = None

    def __post_init__(self):
        if type(self.completed) is not bool:
            raise TypeError("completed must be boolean")


class ExecutionBackend(Protocol):
    """Persistent worker lifecycle, case execution and native reporting.

    start/close own reusable resources. execute_case owns per-request state,
    timeout enforcement and cancellation cleanup. Cases are opaque IDs; neither
    model loading nor reset/step/reward is imposed by the engine.
    """
    cases: Sequence[str]
    supports_timeout: bool

    def check(self, config) -> Sequence[str]: ...
    def start(self, config) -> None: ...
    def execute_case(self, case: str, *, attempt: int, config) -> CaseResult: ...
    def record(self, case: str, result: CaseResult, *, attempt: int) -> None: ...
    def close(self) -> None: ...
    def finish(self) -> Any: ...
