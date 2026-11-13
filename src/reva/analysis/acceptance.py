from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .overhead import ExecutionOverhead


@dataclass(frozen=True)
class AcceptanceCheck:
    """One explicit scientific-contract gate and the evidence supporting it."""

    requirement: str
    passed: bool
    evidence: str
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "passed": self.passed,
            "evidence": self.evidence,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class EvaluationAcceptanceReport:
    """Conservative report for the proposal's executable acceptance criteria."""

    checks: tuple[AcceptanceCheck, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "reva_evaluation_acceptance_v1",
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }


def audit_evaluation_acceptance(
    campaign_audit: Any,
    *,
    policy_transparent: bool | None = None,
    reproducible: bool | None = None,
    recovery_verified: bool | None = None,
    statistical_validity: bool | None = None,
    execution_overhead: ExecutionOverhead | None = None,
) -> EvaluationAcceptanceReport:
    """Evaluate every acceptance gate without treating absent evidence as success.

    The campaign audit supplies facts that ReVa can establish locally;
    callers must explicitly provide parity, recovery, reproducibility, and
    statistical evidence produced by their respective protocols.
    """
    outcome = getattr(campaign_audit, "outcome_provenance", None)
    authoritative = bool(outcome and outcome.authoritative_scorer_declared)
    overhead = execution_overhead or getattr(campaign_audit, "execution_overhead", None)
    checks = (
        _boolean_check("policy_transparency", policy_transparent, "policy parity report"),
        AcceptanceCheck(
            "attempt_integrity",
            bool(getattr(campaign_audit, "attempts_complete", False)),
            "campaign ledger audit",
            ()
            if getattr(campaign_audit, "attempts_complete", False)
            else ("attempts are incomplete",),
        ),
        _boolean_check("reproducibility", reproducible, "frozen plan and revision manifest"),
        _boolean_check("failure_recovery", recovery_verified, "recovery audit"),
        AcceptanceCheck(
            "timing_correctness",
            bool(overhead and overhead.provenance_complete),
            "timing provenance",
            ()
            if overhead and overhead.provenance_complete
            else ("clock/boundary provenance is absent",),
        ),
        AcceptanceCheck(
            "benchmark_fidelity",
            authoritative,
            "authoritative outcome ledger",
            () if authoritative else ("authoritative scorer evidence is absent",),
        ),
        _boolean_check("statistical_validity", statistical_validity, "paired/stratified analysis"),
        AcceptanceCheck(
            "evidence_validity",
            bool(getattr(campaign_audit, "evidence_verified", False)),
            "artifact and runtime receipt verification",
            ()
            if getattr(campaign_audit, "evidence_verified", False)
            else ("trusted evidence verification failed",),
        ),
        AcceptanceCheck(
            "execution_overhead",
            bool(overhead and overhead.valid and overhead.provenance_complete),
            "matched baseline/instrumented timing report",
            ()
            if overhead and overhead.valid and overhead.provenance_complete
            else ("valid overhead report with provenance is absent",),
        ),
    )
    return EvaluationAcceptanceReport(checks)


def _boolean_check(requirement: str, value: bool | None, evidence: str) -> AcceptanceCheck:
    return AcceptanceCheck(
        requirement,
        value is True,
        evidence,
        () if value is True else ("evidence was not supplied or did not pass",),
    )
