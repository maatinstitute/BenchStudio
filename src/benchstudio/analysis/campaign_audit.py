from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..campaigns.frozen_plan import FrozenCampaignPlan
from .claims import ClaimDecision, ClaimType, validate_claim
from .outcomes import OutcomeProvenanceAudit, OutcomeRecord, audit_outcome_provenance

_FINAL_STATUSES = {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class CampaignAudit:
    planned_attempts: int
    recorded_attempts: int
    missing_attempt_ids: tuple[str, ...]
    duplicate_attempt_ids: tuple[str, ...]
    unknown_attempt_ids: tuple[str, ...]
    status_counts: dict[str, int]
    attempts_complete: bool
    evidence_verified: bool
    claim: ClaimDecision
    outcome_provenance: OutcomeProvenanceAudit | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "planned_attempts": self.planned_attempts,
            "recorded_attempts": self.recorded_attempts,
            "missing_attempt_ids": list(self.missing_attempt_ids),
            "duplicate_attempt_ids": list(self.duplicate_attempt_ids),
            "unknown_attempt_ids": list(self.unknown_attempt_ids),
            "status_counts": dict(self.status_counts),
            "attempts_complete": self.attempts_complete,
            "evidence_verified": self.evidence_verified,
            "claim": self.claim.to_dict(),
            "outcome_provenance": (
                self.outcome_provenance.to_dict() if self.outcome_provenance is not None else None
            ),
        }


def audit_campaign(
    plan: FrozenCampaignPlan,
    records: Iterable[dict[str, Any]],
    *,
    claim_type: ClaimType,
    evidence: dict[str, Any] | None = None,
    outcome_records: Iterable[OutcomeRecord] | None = None,
) -> CampaignAudit:
    """Audit frozen-plan accounting and derive claim prerequisites."""
    rows = list(records)
    planned_ids = {attempt.key.attempt_id for attempt in plan.attempts}
    occurrences: dict[str, int] = {}
    statuses: dict[str, int] = {}
    unknown: set[str] = set()
    for row in rows:
        attempt_id = row.get("attempt_id")
        if not isinstance(attempt_id, str):
            unknown.add(str(attempt_id))
            continue
        occurrences[attempt_id] = occurrences.get(attempt_id, 0) + 1
        if attempt_id not in planned_ids:
            unknown.add(attempt_id)
        status = str(row.get("status", "missing_status"))
        statuses[status] = statuses.get(status, 0) + 1
    duplicates = tuple(sorted(attempt_id for attempt_id, count in occurrences.items() if count > 1))
    missing = tuple(sorted(planned_ids - occurrences.keys()))
    attempts_complete = (
        not missing
        and not duplicates
        and not unknown
        and all(status in _FINAL_STATUSES for status in statuses)
        and len(rows) == len(planned_ids)
    )
    trusted = bool(rows) and all(row.get("evidence_verified") is True for row in rows)
    outcome_list = list(outcome_records) if outcome_records is not None else None
    outcome_audit = audit_outcome_provenance(outcome_list) if outcome_list is not None else None
    claim_evidence = dict(evidence or {})
    provenance_matches_plan = True
    if outcome_audit is not None:
        outcome_ids = {record.attempt_id for record in outcome_list or ()}
        provenance_matches_plan = outcome_ids == planned_ids
    claim_evidence.update(
        {
            "attempts_complete": attempts_complete,
            "trusted_artifacts": trusted,
            "outcome_present": (
                outcome_audit.outcome_present
                if outcome_audit is not None
                else bool(rows)
                and all(row.get("status") in {"completed", "failed", "cancelled"} for row in rows)
            ),
        }
    )
    if outcome_audit is not None:
        claim_evidence["authoritative_scorer_declared"] = (
            outcome_audit.authoritative_scorer_declared and provenance_matches_plan
        )
    decision = validate_claim(claim_type, claim_evidence)
    return CampaignAudit(
        len(planned_ids),
        len(rows),
        missing,
        duplicates,
        tuple(sorted(unknown)),
        statuses,
        attempts_complete,
        trusted,
        decision,
        outcome_audit,
    )
