"""Deterministic counterexample search plans and greedy minimization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
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

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def load_search_plan(path: Path) -> FrozenSearchPlan:
    """Load and validate a serialized frozen counterexample-search plan."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "benchstudio.counterexample_search.v1"
    ):
        raise ValueError("unsupported counterexample search plan schema")
    cases_payload = payload.get("cases")
    if not isinstance(cases_payload, list):
        raise ValueError("counterexample search plan cases must be a list")
    cases: list[SearchCase] = []
    for value in cases_payload:
        if not isinstance(value, dict) or not isinstance(value.get("parameters"), dict):
            raise ValueError("counterexample search case must contain mapping parameters")
        try:
            cases.append(
                SearchCase(
                    str(value["case_id"]),
                    str(value["scenario_id"]),
                    str(value["base_condition_id"]),
                    int(value["seed"]),
                    dict(value["parameters"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid counterexample search case") from exc
    try:
        plan = FrozenSearchPlan(
            str(payload["run_id"]),
            str(payload["scenario_id"]),
            tuple(cases),
            str(payload["plan_digest_sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid counterexample search plan") from exc
    issues = validate_search_plan(plan)
    if issues:
        raise ValueError("invalid counterexample search plan: " + "; ".join(issues))
    return plan


@dataclass(frozen=True)
class MinimizedCounterexample:
    parameters: dict[str, Any]
    tested_candidates: int
    minimized: bool
    failure_preserved: bool


@dataclass(frozen=True)
class SearchEvaluation:
    """Evaluator output for one frozen search case."""

    failed: bool
    failure_digest_sha256: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SearchCaseResult:
    """Immutable, digest-addressable result of evaluating one search case."""

    case_id: str
    scenario_id: str
    base_condition_id: str
    seed: int
    parameters: dict[str, Any]
    failed: bool
    failure_digest_sha256: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "scenario_id": self.scenario_id,
            "base_condition_id": self.base_condition_id,
            "seed": self.seed,
            "parameters": self.parameters,
            "failed": self.failed,
            "failure_digest_sha256": self.failure_digest_sha256,
            "metadata": self.metadata,
        }


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


def execute_search_plan(
    plan: FrozenSearchPlan,
    evaluator: Callable[[SearchCase], SearchEvaluation],
    *,
    output: Path | None = None,
) -> tuple[SearchCaseResult, ...]:
    """Evaluate every frozen search case and optionally persist search evidence.

    The evaluator owns simulator/model execution. BenchStudio owns case order,
    identity, failure digest normalization, and the immutable result record.
    A failed case may provide a digest over its trace; when omitted, a stable
    digest over the case and evaluator metadata is generated.
    """
    issues = validate_search_plan(plan)
    if issues:
        raise ValueError("invalid search plan: " + "; ".join(issues))
    results: list[SearchCaseResult] = []
    for case in plan.cases:
        evaluation = evaluator(case)
        if not isinstance(evaluation, SearchEvaluation):
            raise TypeError("search evaluator must return SearchEvaluation")
        metadata = dict(evaluation.metadata or {})
        failure_digest = evaluation.failure_digest_sha256
        if evaluation.failed:
            if failure_digest is None:
                failure_digest = _digest({"case": asdict(case), "metadata": metadata})
            _require_sha256(failure_digest, "failure_digest_sha256")
        elif failure_digest is not None:
            raise ValueError(f"successful case {case.case_id} cannot have a failure digest")
        results.append(
            SearchCaseResult(
                case.case_id,
                case.scenario_id,
                case.base_condition_id,
                case.seed,
                dict(case.parameters),
                evaluation.failed,
                failure_digest,
                metadata,
            )
        )
    frozen_results = tuple(results)
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        with (output / "search-results.jsonl").open("w", encoding="utf-8") as handle:
            for result in frozen_results:
                handle.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
        summary = {
            "schema": "benchstudio.counterexample_search_results.v1",
            "run_id": plan.run_id,
            "plan_digest_sha256": plan.plan_digest_sha256,
            "result_digest_sha256": _digest([result.to_dict() for result in frozen_results]),
            "scheduled_case_count": len(frozen_results),
            "completed_case_count": len(frozen_results),
            "failed_case_count": sum(result.failed for result in frozen_results),
        }
        (output / "search-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return frozen_results


def build_search_candidates(
    plan: FrozenSearchPlan, results: Iterable[SearchCaseResult]
) -> tuple[Any, ...]:
    """Convert only observed failures into candidates for separate confirmation."""
    from .confirmation import SearchCandidate

    by_id = {case.case_id: case for case in plan.cases}
    candidates: list[SearchCandidate] = []
    for result in results:
        case = by_id.get(result.case_id)
        if case is None:
            raise ValueError(f"search result is outside the frozen plan: {result.case_id}")
        if not result.failed:
            continue
        if result.failure_digest_sha256 is None:
            raise ValueError(f"failed search case has no failure digest: {result.case_id}")
        candidate_id = (
            "candidate-"
            + _digest(
                {
                    "run_id": plan.run_id,
                    "case_id": case.case_id,
                    "failure": result.failure_digest_sha256,
                }
            )[:16]
        )
        candidates.append(
            SearchCandidate(
                candidate_id,
                case.scenario_id,
                case.case_id,
                plan.run_id,
                case.seed,
                result.failure_digest_sha256,
            )
        )
    return tuple(candidates)


def validate_search_plan(plan: FrozenSearchPlan) -> list[str]:
    """Validate a serialized or transported search plan before execution."""
    issues: list[str] = []
    if not plan.run_id:
        issues.append("run_id is required")
    if not plan.scenario_id:
        issues.append("scenario_id is required")
    case_ids = [case.case_id for case in plan.cases]
    if len(set(case_ids)) != len(case_ids):
        issues.append("search case IDs must be unique")
    for case in plan.cases:
        if case.scenario_id != plan.scenario_id:
            issues.append(f"case {case.case_id}: scenario_id differs from plan")
        if not case.case_id or not case.base_condition_id:
            issues.append(f"case {case.case_id}: identity fields are required")
    expected = _digest([asdict(case) for case in plan.cases])
    if expected != plan.plan_digest_sha256:
        issues.append("plan_digest_sha256 does not match cases")
    return issues


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _require_sha256(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")
