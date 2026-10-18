from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from .frozen_plan import FrozenCampaignPlan


@dataclass(frozen=True)
class Intervention:
    intervention_id: str
    transition_index: int
    kind: str
    parameters: dict[str, Any]

    def __post_init__(self) -> None:
        if self.transition_index < 0:
            raise ValueError("transition_index must be non-negative")


@dataclass(frozen=True)
class CounterfactualCell:
    pair_id: str
    nominal_attempt_id: str
    branch_attempt_id: str
    intervention: Intervention
    branch: Literal["nominal", "intervention"] = "intervention"


@dataclass(frozen=True)
class CounterfactualPair:
    nominal: CounterfactualCell
    intervention: CounterfactualCell


@dataclass(frozen=True)
class FrozenCounterfactualPlan:
    run_id: str
    source_plan_digest_sha256: str
    pairs: tuple[CounterfactualPair, ...]
    plan_digest_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "benchstudio.counterfactual.v1",
            "run_id": self.run_id,
            "source_plan_digest_sha256": self.source_plan_digest_sha256,
            "pairs": [asdict(pair) for pair in self.pairs],
            "plan_digest_sha256": self.plan_digest_sha256,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


@dataclass(frozen=True)
class CounterfactualEvaluation:
    """Evaluator output for one nominal or intervention branch."""

    success: bool | None
    recovery_time_ms: float | None = None
    failure_category: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CounterfactualBranchResult:
    """Evidence record retaining the frozen branch lineage."""

    branch_attempt_id: str
    pair_id: str
    nominal_attempt_id: str
    branch: Literal["nominal", "intervention"]
    transition_index: int
    intervention_id: str
    success: bool | None
    recovery_time_ms: float | None
    failure_category: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compile_counterfactual_plan(
    nominal_plan: FrozenCampaignPlan, interventions: Iterable[Intervention]
) -> FrozenCounterfactualPlan:
    """Freeze intervention branches against an existing nominal campaign."""
    rows = tuple(interventions)
    if not rows:
        raise ValueError("at least one intervention is required")
    if any(item.intervention_id == "none" for item in rows):
        raise ValueError("intervention id 'none' is reserved for nominal cells")
    if len({item.intervention_id for item in rows}) != len(rows):
        raise ValueError("intervention IDs must be unique")
    pairs: list[CounterfactualPair] = []
    for attempt in nominal_plan.attempts:
        for intervention in rows:
            nominal = CounterfactualCell(
                attempt.key.pair_id,
                attempt.key.attempt_id,
                attempt.key.attempt_id,
                Intervention("none", intervention.transition_index, "none", {}),
                "nominal",
            )
            branch_id = (
                "cf-"
                + _digest(
                    {
                        "nominal_attempt_id": attempt.key.attempt_id,
                        "intervention": asdict(intervention),
                    }
                )[:16]
            )
            pairs.append(
                CounterfactualPair(
                    nominal,
                    CounterfactualCell(
                        attempt.key.pair_id,
                        attempt.key.attempt_id,
                        branch_id,
                        intervention,
                    ),
                )
            )
    payload = {
        "source_plan_digest_sha256": nominal_plan.plan_digest_sha256,
        "pairs": [asdict(pair) for pair in pairs],
    }
    return FrozenCounterfactualPlan(
        nominal_plan.run_id,
        nominal_plan.plan_digest_sha256,
        tuple(pairs),
        _digest(payload),
    )


def validate_counterfactual_plan(plan: FrozenCounterfactualPlan) -> list[str]:
    issues: list[str] = []
    if not plan.pairs:
        issues.append("counterfactual plan must contain at least one pair")
    for index, pair in enumerate(plan.pairs):
        issues.extend(
            f"pair {index}: {issue}"
            for issue in validate_counterfactual_pair(pair.nominal, pair.intervention)
        )
    expected = _digest(
        {
            "source_plan_digest_sha256": plan.source_plan_digest_sha256,
            "pairs": [asdict(pair) for pair in plan.pairs],
        }
    )
    if expected != plan.plan_digest_sha256:
        issues.append("plan_digest_sha256 does not match pairs")
    return issues


def execute_counterfactual_plan(
    plan: FrozenCounterfactualPlan,
    evaluator: Any,
    *,
    output: Path | None = None,
) -> tuple[CounterfactualBranchResult, ...]:
    """Execute nominal and intervention branches through an external evaluator.

    The evaluator owns simulator state and disturbance application. BenchStudio
    controls branch order, frozen lineage, result serialization, and paired
    accounting; it never infers a missing outcome as failure.
    """
    issues = validate_counterfactual_plan(plan)
    if issues:
        raise ValueError("invalid counterfactual plan: " + "; ".join(issues))
    results: list[CounterfactualBranchResult] = []
    result_path = None
    handle = None
    error: BaseException | None = None
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        result_path = output / "counterfactual-results.jsonl"
        handle = result_path.open("w", encoding="utf-8")
    try:
        for pair in plan.pairs:
            for cell in (pair.nominal, pair.intervention):
                evaluation = evaluator(cell)
                if not isinstance(evaluation, CounterfactualEvaluation):
                    raise TypeError("counterfactual evaluator must return CounterfactualEvaluation")
                if not isinstance(evaluation.success, (bool, type(None))):
                    raise ValueError("counterfactual success must be boolean or None")
                if evaluation.recovery_time_ms is not None:
                    if (
                        isinstance(evaluation.recovery_time_ms, bool)
                        or not isinstance(evaluation.recovery_time_ms, (int, float))
                        or not math.isfinite(float(evaluation.recovery_time_ms))
                        or evaluation.recovery_time_ms < 0
                    ):
                        raise ValueError("recovery_time_ms must be finite and non-negative")
                if evaluation.failure_category is not None and not isinstance(
                    evaluation.failure_category, str
                ):
                    raise ValueError("failure_category must be a string or None")
                if evaluation.metadata is not None and not isinstance(evaluation.metadata, dict):
                    raise ValueError("counterfactual metadata must be a mapping or None")
                result = CounterfactualBranchResult(
                    cell.branch_attempt_id,
                    cell.pair_id,
                    cell.nominal_attempt_id,
                    cell.branch,
                    cell.intervention.transition_index,
                    cell.intervention.intervention_id,
                    evaluation.success,
                    evaluation.recovery_time_ms,
                    evaluation.failure_category,
                    dict(evaluation.metadata or {}),
                )
                results.append(result)
                if handle is not None:
                    handle.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
                    handle.flush()
    except BaseException as exc:
        error = exc
    finally:
        if handle is not None:
            handle.close()
        if output is not None:
            _write_counterfactual_summary(output, plan, results, error)
    if error is not None:
        raise error
    return tuple(results)


def _write_counterfactual_summary(
    output: Path,
    plan: FrozenCounterfactualPlan,
    results: list[CounterfactualBranchResult],
    error: BaseException | None,
) -> None:
    summary = {
        "schema": "benchstudio.counterfactual_results.v1",
        "run_id": plan.run_id,
        "source_plan_digest_sha256": plan.source_plan_digest_sha256,
        "plan_digest_sha256": plan.plan_digest_sha256,
        "result_digest_sha256": _digest([result.to_dict() for result in results]),
        "scheduled_branch_count": sum(2 for _ in plan.pairs),
        "completed_branch_count": len(results),
        "missing_branch_count": sum(2 for _ in plan.pairs) - len(results),
        "unknown_outcome_count": sum(result.success is None for result in results),
        "status": "failed" if error is not None else "completed",
    }
    if error is not None:
        summary["error"] = f"{type(error).__name__}: {error}"
    (output / "counterfactual-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def validate_counterfactual_pair(
    nominal: CounterfactualCell, branch: CounterfactualCell
) -> list[str]:
    issues: list[str] = []
    if nominal.pair_id != branch.pair_id:
        issues.append("pair_id differs")
    if nominal.intervention.intervention_id != "none":
        issues.append("nominal cell must use the none intervention")
    if branch.branch != "intervention":
        issues.append("branch cell must be an intervention")
    if nominal.intervention.transition_index != branch.intervention.transition_index:
        issues.append("transition_index differs")
    return issues


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
