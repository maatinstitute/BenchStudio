from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


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
