from __future__ import annotations

import hashlib
import json
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
