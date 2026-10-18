from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..calibration import calibration_from_environment, compare_calibrations
from ..campaigns.frozen_plan import FrozenCampaignPlan
from ..validity import BenchmarkValidityAudit, BenchmarkValidityRecord, audit_benchmark_validity
from .claims import ClaimDecision, ClaimType, validate_claim
from .outcomes import OutcomeProvenanceAudit, OutcomeRecord, audit_outcome_provenance
from .overhead import ExecutionOverhead, load_execution_overhead

_FINAL_STATUSES = {"completed", "failed", "failed_cleanup", "cancelled"}


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
    calibration_issues: tuple[str, ...] = ()
    benchmark_validity: BenchmarkValidityAudit | None = None
    evidence_issues: tuple[str, ...] = ()
    execution_overhead: ExecutionOverhead | None = None

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
            "evidence_issues": list(self.evidence_issues),
            "claim": self.claim.to_dict(),
            "outcome_provenance": (
                self.outcome_provenance.to_dict() if self.outcome_provenance is not None else None
            ),
            "calibration_issues": list(self.calibration_issues),
            "calibration_compatible": not self.calibration_issues,
            "benchmark_validity": (
                self.benchmark_validity.to_dict() if self.benchmark_validity is not None else None
            ),
            "execution_overhead": (
                self.execution_overhead.to_dict() if self.execution_overhead is not None else None
            ),
            "execution_overhead_valid": (
                self.execution_overhead is not None
                and self.execution_overhead.valid
                and self.execution_overhead.provenance_complete
            ),
        }


def audit_campaign(
    plan: FrozenCampaignPlan,
    records: Iterable[dict[str, Any]],
    *,
    claim_type: ClaimType,
    evidence: dict[str, Any] | None = None,
    outcome_records: Iterable[OutcomeRecord] | None = None,
    evidence_issues: Iterable[str] = (),
    execution_overhead: ExecutionOverhead | None = None,
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
    evidence_issue_rows = tuple(evidence_issues)
    trusted = (
        bool(rows)
        and all(row.get("evidence_verified") is True for row in rows)
        and not evidence_issue_rows
        and (evidence or {}).get("trusted_artifacts", True) is not False
    )
    outcome_list = list(outcome_records) if outcome_records is not None else None
    outcome_audit = audit_outcome_provenance(outcome_list) if outcome_list is not None else None
    claim_evidence = dict(evidence or {})
    calibration_issues = _plan_calibration_issues(plan)
    benchmark_validity = _plan_benchmark_validity(plan, planned_ids)
    if claim_type in {ClaimType.PAIRED_COMPARISON, ClaimType.REAL_WORLD_TRANSFER}:
        if calibration_issues or benchmark_validity is None or not benchmark_validity.valid:
            claim_evidence["semantic_match"] = False
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
        tuple(calibration_issues),
        benchmark_validity,
        evidence_issue_rows,
        execution_overhead,
    )


def audit_campaign_directory(
    root: Path,
    *,
    claim_type: ClaimType = ClaimType.SINGLE_RUN_OUTCOME,
    evidence: dict[str, Any] | None = None,
    execution_overhead: ExecutionOverhead | None = None,
) -> CampaignAudit:
    """Audit an existing campaign directory without constructing adapters."""
    from ..campaigns.frozen_plan import load_frozen_campaign_plan
    from ..campaigns.ledger import AttemptLedger
    from ..evidence import verify_artifact_manifest
    from ..runtime_receipts import load_runtime_receipt, verify_runtime_receipt
    from .outcomes import OutcomeLedger

    plan = load_frozen_campaign_plan(root / "campaign-plan.json")
    ledger = AttemptLedger(root / "attempt-results.jsonl", plan)
    records = ledger.records
    by_attempt = {record.get("attempt_id"): record for record in records}
    evidence_issues: list[str] = []
    if execution_overhead is None:
        overhead_path = root / "execution-overhead.json"
        if overhead_path.is_file():
            try:
                execution_overhead = load_execution_overhead(overhead_path)
            except (OSError, ValueError, TypeError) as exc:
                evidence_issues.append(f"execution overhead is invalid: {exc}")
    for attempt in plan.attempts:
        attempt_id = attempt.key.attempt_id
        record = by_attempt.get(attempt_id)
        if record is None or record.get("status") == "cancelled":
            continue
        attempt_dir = root / "attempts" / attempt_id
        verification = verify_artifact_manifest(attempt_dir)
        if not verification["valid"]:
            evidence_issues.append(
                f"{attempt_id}: artifact manifest is invalid: {verification['mismatches']}"
            )
            continue
        receipt_path = attempt_dir / "runtime-receipt.json"
        receipt_check = verify_runtime_receipt(receipt_path)
        if not receipt_check["valid"]:
            evidence_issues.append(f"{attempt_id}: runtime receipt is invalid")
            continue
        receipt = load_runtime_receipt(receipt_path)
        for field, expected in (
            ("run_id", plan.run_id),
            ("attempt_id", attempt_id),
            ("plan_digest_sha256", plan.plan_digest_sha256),
        ):
            if receipt.get(field) != expected:
                evidence_issues.append(
                    f"{attempt_id}: runtime receipt {field} does not match frozen plan"
                )
    claim_evidence = dict(evidence or {})
    claim_evidence["trusted_artifacts"] = not evidence_issues
    outcome_records = None
    outcomes_path = root / "outcomes.jsonl"
    if outcomes_path.is_file():
        outcome_records = OutcomeLedger(
            outcomes_path,
            attempt_ids=frozenset(attempt.key.attempt_id for attempt in plan.attempts),
            plan_digest_sha256=plan.plan_digest_sha256,
        ).records
    return audit_campaign(
        plan,
        records,
        claim_type=claim_type,
        evidence=claim_evidence,
        outcome_records=outcome_records,
        evidence_issues=evidence_issues,
        execution_overhead=execution_overhead,
    )


def _plan_benchmark_validity(
    plan: FrozenCampaignPlan, planned_ids: set[str]
) -> BenchmarkValidityAudit | None:
    evaluation = (plan.protocol or {}).get("P", {}).get("evaluation", {})
    value = evaluation.get("validity")
    if value is None:
        return None
    try:
        record = BenchmarkValidityRecord.from_mapping(value)
    except ValueError as exc:
        return BenchmarkValidityAudit(False, (str(exc),), ())
    return audit_benchmark_validity(record, planned_ids)


def _plan_calibration_issues(plan: FrozenCampaignPlan) -> tuple[str, ...]:
    environments = (plan.protocol or {}).get("S", {}).get("environments", [])
    if not isinstance(environments, list) or len(environments) < 2:
        return ()
    records = []
    issues: list[str] = []
    for environment in environments:
        if not isinstance(environment, dict):
            issues.append("environment declaration is not a mapping")
            continue
        default_enabled = environment.get("kind") != "physical"
        if not environment.get("enabled", default_enabled):
            continue
        environment_id = environment.get("id", "<unknown>")
        try:
            calibration = calibration_from_environment(environment)
        except ValueError as exc:
            issues.append(f"{environment_id}: invalid calibration: {exc}")
            continue
        if calibration is None:
            issues.append(f"{environment_id}: calibration is missing")
        else:
            records.append((environment_id, calibration))
    for index, (first_id, first) in enumerate(records):
        for second_id, second in records[index + 1 :]:
            comparison = compare_calibrations(first, second)
            issues.extend(f"{first_id} vs {second_id}: {issue}" for issue in comparison.issues)
    return tuple(issues)
