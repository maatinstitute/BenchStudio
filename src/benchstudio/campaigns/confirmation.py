from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


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
            "schema": "benchstudio.confirmation.v1",
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
    seeds = tuple(int(seed) for seed in confirmation_seeds)
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
    if len(set(case_ids)) != len(case_ids):
        issues.append("confirmation case IDs must be unique")
    expected = _digest([asdict(case) for case in plan.cases])
    if expected != plan.plan_digest_sha256:
        issues.append("plan_digest_sha256 does not match cases")
    return issues


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
