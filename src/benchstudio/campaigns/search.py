"""Deterministic counterexample search plans and greedy minimization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class PerturbationDimension:
    name: str
    values: tuple[Any, ...]


@dataclass(frozen=True)
class SearchCase:
    case_id: str
    scenario_id: str
    base_condition_id: str
    seed: int
    parameters: dict[str, Any]


@dataclass(frozen=True)
class FrozenSearchPlan:
    run_id: str
    scenario_id: str
    cases: tuple[SearchCase, ...]
    plan_digest_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "benchstudio.counterexample_search.v1",
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "cases": [asdict(case) for case in self.cases],
            "plan_digest_sha256": self.plan_digest_sha256,
        }


@dataclass(frozen=True)
class MinimizedCounterexample:
    parameters: dict[str, Any]
    tested_candidates: int
    minimized: bool
    failure_preserved: bool


def compile_search_plan(
    *,
    run_id: str,
    scenario_id: str,
    base_condition_id: str,
    dimensions: Iterable[PerturbationDimension],
    seeds: Iterable[int],
    max_cases: int | None = None,
) -> FrozenSearchPlan:
    """Freeze admissible search cases with a stable hash-keyed order."""
    if not run_id or not scenario_id or not base_condition_id:
        raise ValueError("run_id, scenario_id, and base_condition_id are required")
    dimensions = tuple(dimensions)
    if not dimensions or any(
        not dimension.name or not dimension.values for dimension in dimensions
    ):
        raise ValueError("dimensions must have non-empty names and values")
    if len({dimension.name for dimension in dimensions}) != len(dimensions):
        raise ValueError("dimension names must be unique")
    seeds = tuple(int(seed) for seed in seeds)
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be non-empty and unique")
    combinations: list[dict[str, Any]] = [{}]
    for dimension in dimensions:
        expanded: list[dict[str, Any]] = []
        for partial in combinations:
            for value in dimension.values:
                expanded.append({**partial, dimension.name: value})
        combinations = expanded
    candidates = [(seed, parameters) for seed in seeds for parameters in combinations]
    candidates.sort(key=lambda item: (_digest([run_id, scenario_id, item]), item))
    if max_cases is not None:
        if max_cases < 1:
            raise ValueError("max_cases must be positive")
        candidates = candidates[:max_cases]
    cases = tuple(
        SearchCase(
            _digest([run_id, scenario_id, base_condition_id, seed, parameters])[:16],
            scenario_id,
            base_condition_id,
            seed,
            parameters,
        )
        for seed, parameters in candidates
    )
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("search case identity collision")
    return FrozenSearchPlan(run_id, scenario_id, cases, _digest([asdict(case) for case in cases]))


def minimize_counterexample(
    parameters: dict[str, Any],
    failure_predicate: Callable[[dict[str, Any]], bool],
    *,
    candidate_values: dict[str, Iterable[Any]],
) -> MinimizedCounterexample:
    """Greedily minimize a failing parameter vector in stable key order."""
    current = dict(parameters)
    if not failure_predicate(dict(current)):
        return MinimizedCounterexample(current, 1, False, False)
    tested = 1
    changed = False
    for name in sorted(candidate_values):
        for value in candidate_values[name]:
            if name not in current or current[name] == value:
                continue
            candidate = {**current, name: value}
            tested += 1
            if failure_predicate(dict(candidate)):
                current = candidate
                changed = True
                break
    return MinimizedCounterexample(current, tested, changed, True)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
