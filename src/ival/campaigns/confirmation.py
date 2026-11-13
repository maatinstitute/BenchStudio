from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


def _require_exact_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


@dataclass(frozen=True)
class SearchCandidate:
    candidate_id: str
    scenario_id: str
    initial_condition_id: str
    source_run_id: str
    source_seed: int
    failure_digest_sha256: str
    admissible: bool = True


@dataclass(frozen=True)
class ConfirmationCase:
    case_id: str
    candidate_id: str
    scenario_id: str
    initial_condition_id: str
    confirmation_seed: int
    source_search_run_id: str


@dataclass(frozen=True)
class FrozenConfirmationPlan:
    run_id: str
    source_search_digest_sha256: str
    cases: tuple[ConfirmationCase, ...]
    plan_digest_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "ival.confirmation.v1",
            "run_id": self.run_id,
            "source_search_digest_sha256": self.source_search_digest_sha256,
            "cases": [asdict(case) for case in self.cases],
            "plan_digest_sha256": self.plan_digest_sha256,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def load_confirmation_plan(path: Path) -> FrozenConfirmationPlan:
    """Load and validate a serialized independent confirmation plan."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != "ival.confirmation.v1":
        raise ValueError("unsupported confirmation plan schema")
    cases_payload = payload.get("cases")
    if not isinstance(cases_payload, list):
        raise ValueError("confirmation plan cases must be a list")
    cases: list[ConfirmationCase] = []
    for value in cases_payload:
        if not isinstance(value, dict):
            raise ValueError("confirmation case must be a mapping")
        try:
            cases.append(
                ConfirmationCase(
                    str(value["case_id"]),
                    str(value["candidate_id"]),
                    str(value["scenario_id"]),
                    str(value["initial_condition_id"]),
                    _require_exact_int(value["confirmation_seed"], "confirmation seed"),
                    str(value["source_search_run_id"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid confirmation case") from exc
    try:
        plan = FrozenConfirmationPlan(
            str(payload["run_id"]),
            str(payload["source_search_digest_sha256"]),
            tuple(cases),
            str(payload["plan_digest_sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid confirmation plan") from exc
    issues = validate_confirmation_plan(plan)
    if issues:
        raise ValueError("invalid confirmation plan: " + "; ".join(issues))
    return plan


@dataclass(frozen=True)
class ConfirmationEvaluation:
    """Evaluator output for one independent holdout case."""

    failure_reproduced: bool
    failure_digest_sha256: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ConfirmationCaseResult:
    """Immutable result linked to both the confirmation and search plans."""

    case_id: str
    candidate_id: str
    scenario_id: str
    initial_condition_id: str
    confirmation_seed: int
    source_search_run_id: str
    failure_reproduced: bool
    failure_digest_sha256: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConfirmationResultAudit:
    scheduled_cases: int
    recorded_cases: int
    missing_case_ids: tuple[str, ...]
    unknown_case_ids: tuple[str, ...]
    duplicate_case_ids: tuple[str, ...]
    lineage_issues: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return (
            not (
                self.missing_case_ids
                or self.unknown_case_ids
                or self.duplicate_case_ids
                or self.lineage_issues
            )
            and self.recorded_cases == self.scheduled_cases
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheduled_cases": self.scheduled_cases,
            "recorded_cases": self.recorded_cases,
            "missing_case_ids": list(self.missing_case_ids),
            "unknown_case_ids": list(self.unknown_case_ids),
            "duplicate_case_ids": list(self.duplicate_case_ids),
            "lineage_issues": list(self.lineage_issues),
            "complete": self.complete,
        }


def load_confirmation_results(path: Path) -> list[dict[str, Any]]:
    """Load confirmation result rows from JSON, JSONL, or NDJSON."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        values = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        values = json.loads(text)
        if isinstance(values, dict):
            values = values.get("records")
    if not isinstance(values, list) or not all(isinstance(value, dict) for value in values):
        raise ValueError("confirmation results must be a JSON array or {records: [...]} mapping")
    return values


def audit_confirmation_results(
    plan: FrozenConfirmationPlan, records: list[dict[str, Any]]
) -> ConfirmationResultAudit:
    """Verify confirmation identity and reproduction evidence against a holdout plan."""
    expected = {
        case.case_id: (
            case.candidate_id,
            case.scenario_id,
            case.initial_condition_id,
            case.confirmation_seed,
            case.source_search_run_id,
        )
        for case in plan.cases
    }
    occurrences: dict[str, int] = {}
    unknown: set[str] = set()
    lineage: list[str] = []
    for index, record in enumerate(records):
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            lineage.append(f"record {index}: missing case_id")
            continue
        occurrences[case_id] = occurrences.get(case_id, 0) + 1
        expected_row = expected.get(case_id)
        if expected_row is None:
            unknown.add(case_id)
            continue
        reproduced = record.get("failure_reproduced")
        failure_digest = record.get("failure_digest_sha256")
        if not isinstance(reproduced, bool):
            lineage.append(f"{case_id}: failure_reproduced must be a boolean")
        elif reproduced and failure_digest is None:
            lineage.append(f"{case_id}: reproduced failure requires failure_digest_sha256")
        elif not reproduced and failure_digest is not None:
            lineage.append(f"{case_id}: non-reproducing result cannot have failure_digest_sha256")
        if failure_digest is not None and (
            not isinstance(failure_digest, str)
            or len(failure_digest) != 64
            or any(character not in "0123456789abcdef" for character in failure_digest)
        ):
            lineage.append(
                f"{case_id}: failure_digest_sha256 must be a lowercase SHA-256 hex digest"
            )
        for field, value in zip(
            (
                "candidate_id",
                "scenario_id",
                "initial_condition_id",
                "confirmation_seed",
                "source_search_run_id",
            ),
            expected_row,
        ):
            if record.get(field) != value:
                lineage.append(f"{case_id}: {field} does not match frozen plan")
    return ConfirmationResultAudit(
        len(expected),
        len(records),
        tuple(sorted(set(expected) - occurrences.keys())),
        tuple(sorted(unknown)),
        tuple(sorted(case_id for case_id, count in occurrences.items() if count > 1)),
        tuple(lineage),
    )


def compile_confirmation_plan(
    *,
    run_id: str,
    source_search_digest_sha256: str,
    candidates: Iterable[SearchCandidate],
    confirmation_seeds: Iterable[int],
    holdout_candidate_ids: Iterable[str] | None = None,
) -> FrozenConfirmationPlan:
    """Freeze an independent confirmation matrix from search discoveries."""
    if not run_id:
        raise ValueError("run_id is required")
    _require_sha256(source_search_digest_sha256, "source_search_digest_sha256")
    candidate_rows = list(candidates)
    if not candidate_rows:
        raise ValueError("at least one search candidate is required")
    if len({candidate.candidate_id for candidate in candidate_rows}) != len(candidate_rows):
        raise ValueError("candidate IDs must be unique")
    seeds = tuple(_require_exact_int(seed, "confirmation seed") for seed in confirmation_seeds)
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("confirmation seeds must be non-empty and unique")
    selected_ids = (
        set(holdout_candidate_ids)
        if holdout_candidate_ids is not None
        else {candidate.candidate_id for candidate in candidate_rows}
    )
    candidates_by_id = {candidate.candidate_id: candidate for candidate in candidate_rows}
    unknown = selected_ids - candidates_by_id.keys()
    if unknown:
        raise ValueError(f"holdout contains unknown candidate IDs: {sorted(unknown)}")
    selected = [candidates_by_id[candidate_id] for candidate_id in sorted(selected_ids)]
    cases: list[ConfirmationCase] = []
    for candidate in selected:
        if not candidate.admissible:
            raise ValueError(
                f"candidate is not admissible for confirmation: {candidate.candidate_id}"
            )
        if candidate.source_seed in seeds:
            raise ValueError(
                f"confirmation seed reuses search seed for candidate {candidate.candidate_id}"
            )
        for seed in seeds:
            case_id = _digest(
                {
                    "run_id": run_id,
                    "candidate_id": candidate.candidate_id,
                    "confirmation_seed": seed,
                }
            )[:16]
            cases.append(
                ConfirmationCase(
                    case_id,
                    candidate.candidate_id,
                    candidate.scenario_id,
                    candidate.initial_condition_id,
                    seed,
                    candidate.source_run_id,
                )
            )
    cases.sort(key=lambda case: (_digest(asdict(case)), case.case_id))
    digest = _digest([asdict(case) for case in cases])
    return FrozenConfirmationPlan(run_id, source_search_digest_sha256, tuple(cases), digest)


def validate_confirmation_plan(plan: FrozenConfirmationPlan) -> list[str]:
    issues: list[str] = []
    if not plan.run_id:
        issues.append("run_id is required")
    try:
        _require_sha256(plan.source_search_digest_sha256, "source_search_digest_sha256")
    except ValueError as exc:
        issues.append(str(exc))
    case_ids = [case.case_id for case in plan.cases]
    if not plan.cases:
        issues.append("confirmation plan must contain at least one case")
    if len(set(case_ids)) != len(case_ids):
        issues.append("confirmation case IDs must be unique")
    for case in plan.cases:
        if not case.candidate_id or not case.scenario_id or not case.source_search_run_id:
            issues.append(f"case {case.case_id}: identity fields are required")
        if case.confirmation_seed < 0:
            issues.append(f"case {case.case_id}: confirmation_seed must be non-negative")
    expected = _digest([asdict(case) for case in plan.cases])
    if expected != plan.plan_digest_sha256:
        issues.append("plan_digest_sha256 does not match cases")
    return issues


def execute_confirmation_plan(
    plan: FrozenConfirmationPlan,
    evaluator: Any,
    *,
    output: Path | None = None,
) -> tuple[ConfirmationCaseResult, ...]:
    """Evaluate independent holdout cases without changing the search plan.

    The evaluator owns simulator/model execution. IVal records whether
    the discovered failure reproduced, links each result to the frozen source
    search digest, and keeps the confirmation evidence separate from discovery.
    """
    issues = validate_confirmation_plan(plan)
    if issues:
        raise ValueError("invalid confirmation plan: " + "; ".join(issues))
    results: list[ConfirmationCaseResult] = []
    for case in plan.cases:
        evaluation = evaluator(case)
        if not isinstance(evaluation, ConfirmationEvaluation):
            raise TypeError("confirmation evaluator must return ConfirmationEvaluation")
        metadata = dict(evaluation.metadata or {})
        failure_digest = evaluation.failure_digest_sha256
        if evaluation.failure_reproduced:
            if failure_digest is None:
                failure_digest = _digest({"case": asdict(case), "metadata": metadata})
            _require_sha256(failure_digest, "failure_digest_sha256")
        elif failure_digest is not None:
            raise ValueError(f"non-reproducing case {case.case_id} cannot have a failure digest")
        results.append(
            ConfirmationCaseResult(
                case.case_id,
                case.candidate_id,
                case.scenario_id,
                case.initial_condition_id,
                case.confirmation_seed,
                case.source_search_run_id,
                evaluation.failure_reproduced,
                failure_digest,
                metadata,
            )
        )
    frozen_results = tuple(results)
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        with (output / "confirmation-results.jsonl").open("w", encoding="utf-8") as handle:
            for result in frozen_results:
                handle.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
        summary = {
            "schema": "ival.confirmation_results.v1",
            "run_id": plan.run_id,
            "source_search_digest_sha256": plan.source_search_digest_sha256,
            "plan_digest_sha256": plan.plan_digest_sha256,
            "result_digest_sha256": _digest([result.to_dict() for result in frozen_results]),
            "scheduled_case_count": len(frozen_results),
            "completed_case_count": len(frozen_results),
            "failure_reproduced_count": sum(result.failure_reproduced for result in frozen_results),
        }
        (output / "confirmation-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return frozen_results


def _require_sha256(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
