"""Optional episode contracts, independent of model and environment APIs."""
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

from .system_spec import _canonical, _freeze, _thaw
import json


@dataclass(frozen=True)
class EpisodeIsolation:
    """Caller-owned episode boundary, not proof of hidden-memory isolation.

    Select exactly one: reset(system, case), factory(case) context manager
    yielding a fresh system, or an explicit stateless declaration.
    """
    reset: Callable | None = None
    factory: Callable | None = None
    stateless: bool = False

    def __post_init__(self):
        if type(self.stateless) is not bool:
            raise TypeError("stateless must be boolean")
        if sum((self.reset is not None, self.factory is not None, self.stateless)) != 1:
            raise ValueError("select exactly one episode isolation strategy")
        for value in (self.reset, self.factory):
            if value is not None and not callable(value):
                raise TypeError("episode boundary must be callable")

    @property
    def mode(self):
        return "factory" if self.factory else "reset" if self.reset else "declared_stateless"

    @contextmanager
    def activate(self, system, case):
        if self.factory:
            with self.factory(case) as native:
                yield native
        else:
            if self.reset:
                self.reset(system, case)
            yield system


@dataclass(frozen=True)
class ActionBatch:
    """One observation-bound proposal and indices confirmed applied by the backend.

    Payloads are native JSON-compatible evidence; no units or semantics inferred.
    Record indices only after the environment confirms application.
    """
    observation: object
    proposed: tuple
    applied_indices: tuple[int, ...]

    def __post_init__(self):
        if not isinstance(self.proposed, (tuple, list)):
            raise TypeError("proposal must be an ordered action sequence")
        proposed = json.loads(_canonical(_thaw(self.proposed)))
        indices = tuple(self.applied_indices)
        if any(type(i) is not int or i < 0 or i >= len(proposed) for i in indices):
            raise ValueError("applied index outside proposal")
        if tuple(sorted(set(indices))) != indices:
            raise ValueError("applied indices must be unique and ordered")
        object.__setattr__(self, "observation", _freeze(json.loads(_canonical(_thaw(self.observation)))))
        object.__setattr__(self, "proposed", _freeze(proposed))
        object.__setattr__(self, "applied_indices", indices)

    def to_dict(self):
        return {"observation": _thaw(self.observation), "proposed": _thaw(self.proposed),
                "applied_indices": list(self.applied_indices)}


@dataclass(frozen=True)
class EpisodeOutcome:
    """Independent native verdicts; unknown checks remain None."""
    completed: bool
    goal_reached: bool | None = None
    constraints_satisfied: bool | None = None

    def __post_init__(self):
        if type(self.completed) is not bool:
            raise TypeError("completed must be boolean")
        for value in (self.goal_reached, self.constraints_satisfied):
            if value is not None and type(value) is not bool:
                raise TypeError("native verdicts must be boolean or None")


@dataclass(frozen=True)
class EpisodeCoverage:
    planned: tuple[str, ...]
    observed: tuple[str, ...]

    def __post_init__(self):
        for name in ("planned", "observed"):
            values = tuple(getattr(self, name))
            if any(type(v) is not str or not v for v in values) or len(set(values)) != len(values):
                raise ValueError("episode identities must be unique nonempty strings")
            object.__setattr__(self, name, values)
        if not set(self.observed) <= set(self.planned):
            raise ValueError("observed episode outside calendar")

    @property
    def missing(self):
        observed = set(self.observed)
        return tuple(case for case in self.planned if case not in observed)
