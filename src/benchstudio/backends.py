"""Execution contract for persistent workers and interactive evaluation cases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .system_spec import _canonical, _freeze, _thaw


@dataclass(frozen=True)
class BenchmarkCase:
    """An experimental unit and its explicit native execution-group identity.

    Dimensions are declarations supplied by the benchmark (suite/task/state,
    condition/seed, scene, etc.). No task, state or reserved identity is generated.
    """
    case_id: str
    dimensions: Mapping[str, Any]
    execution_id: str | None = None

    def __post_init__(self):
        import json
        if type(self.case_id) is not str or not self.case_id.strip():
            raise ValueError("benchmark case_id must be nonempty")
        execution = self.case_id if self.execution_id is None else self.execution_id
        if type(execution) is not str or not execution.strip():
            raise ValueError("execution_id must be nonempty")
        if not isinstance(self.dimensions, Mapping):
            raise TypeError("case dimensions must be a mapping")
        object.__setattr__(self, "execution_id", execution)
        object.__setattr__(self, "dimensions", _freeze(json.loads(_canonical(_thaw(self.dimensions)))))

    def to_dict(self):
        return {"case_id": self.case_id, "execution_id": self.execution_id,
                "dimensions": _thaw(self.dimensions)}


class BenchmarkProtocol(Protocol):
    """Benchmark-owned native execution, outcome semantics and aggregation.

    bind configures a backend without starting native work. Backend case IDs
    identify execution groups, not necessarily individual experimental units.
    """
    cases: Sequence[BenchmarkCase]
    supports_retries: bool

    def bind(self, system: Any, *, benchmark, config) -> ExecutionBackend: ...


@dataclass(frozen=True)
class CaseResult:
    """Operational completion and backend-owned output, not task success."""
    completed: bool
    output: Any = None
    episodes: tuple = ()

    def __post_init__(self):
        if type(self.completed) is not bool:
            raise TypeError("completed must be boolean")
        from .episodes import EpisodeRecord
        episodes = tuple(self.episodes)
        if any(not isinstance(episode, EpisodeRecord) for episode in episodes):
            raise TypeError("episodes must contain EpisodeRecord")
        if len({episode.case_id for episode in episodes}) != len(episodes):
            raise ValueError("duplicate episode in execution result")
        object.__setattr__(self, "episodes", episodes)


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
