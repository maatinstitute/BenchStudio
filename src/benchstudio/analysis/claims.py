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


def validate_claim(claim_type: ClaimType, evidence: dict[str, Any]) -> ClaimDecision:
    prerequisites = {
        "outcome_present": bool(evidence.get("outcome_present")),
        "authoritative_scorer_declared": bool(evidence.get("authoritative_scorer_declared")),
        "attempts_complete": bool(evidence.get("attempts_complete")),
        "trusted_artifacts": bool(evidence.get("trusted_artifacts")),
        "paired_conditions": bool(evidence.get("paired_conditions")),
        "semantic_match": bool(evidence.get("semantic_match")),
        "uncertainty_reported": bool(evidence.get("uncertainty_reported")),
        "simulation_evidence": bool(evidence.get("simulation_evidence")),
        "physical_evidence": bool(evidence.get("physical_evidence")),
        "transfer_protocol": bool(evidence.get("transfer_protocol")),
    }
    required = {
        ClaimType.SINGLE_RUN_OUTCOME: (
            "outcome_present",
            "authoritative_scorer_declared",
            "trusted_artifacts",
        ),
        ClaimType.PAIRED_COMPARISON: (
            "outcome_present",
            "paired_conditions",
            "semantic_match",
            "uncertainty_reported",
        ),
        ClaimType.REAL_WORLD_TRANSFER: (
            "paired_conditions",
            "semantic_match",
            "simulation_evidence",
            "physical_evidence",
            "transfer_protocol",
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
