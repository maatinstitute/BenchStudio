from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ClaimType(str, Enum):
    SINGLE_RUN_OUTCOME = "single_run_outcome"
    PAIRED_COMPARISON = "paired_comparison"
    REAL_WORLD_TRANSFER = "real_world_transfer"


@dataclass(frozen=True)
class ClaimDecision:
    claim_type: ClaimType
    status: str
    reasons: tuple[str, ...]
    prerequisites: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_type": self.claim_type.value,
            "status": self.status,
            "reasons": list(self.reasons),
            "prerequisites": dict(self.prerequisites),
        }


def validate_claim(claim_type: ClaimType, evidence: dict[str, Any]) -> ClaimDecision:
    """Validate a claim using explicitly boolean, claim-specific evidence.

    Evidence is intentionally fail-closed: strings, numbers, and other truthy
    values are not accepted as affirmative attestations.
    """
    try:
        claim_type = ClaimType(claim_type)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unsupported claim type: {claim_type!r}") from exc
    if not isinstance(evidence, dict):
        raise TypeError("claim evidence must be a mapping")
    prerequisites = {
        name: evidence.get(name) is True
        for name in (
            "outcome_present",
            "authoritative_scorer_declared",
            "attempts_complete",
            "trusted_artifacts",
            "paired_conditions",
            "semantic_match",
            "uncertainty_reported",
            "simulation_evidence",
            "physical_evidence",
            "transfer_protocol",
        )
    }
    required = {
        ClaimType.SINGLE_RUN_OUTCOME: (
            "outcome_present",
            "authoritative_scorer_declared",
            "trusted_artifacts",
            "attempts_complete",
        ),
        ClaimType.PAIRED_COMPARISON: (
            "outcome_present",
            "paired_conditions",
            "semantic_match",
            "uncertainty_reported",
            "attempts_complete",
        ),
        ClaimType.REAL_WORLD_TRANSFER: (
            "outcome_present",
            "authoritative_scorer_declared",
            "trusted_artifacts",
            "paired_conditions",
            "semantic_match",
            "simulation_evidence",
            "physical_evidence",
            "transfer_protocol",
            "attempts_complete",
        ),
    }[claim_type]
    missing = tuple(name for name in required if not prerequisites[name])
    if not missing:
        status = "supported"
    elif claim_type is ClaimType.SINGLE_RUN_OUTCOME and prerequisites["outcome_present"]:
        status = "qualified"
    else:
        status = "unsupported"
    reasons = tuple(f"missing prerequisite: {name}" for name in missing)
    return ClaimDecision(claim_type, status, reasons, prerequisites)
