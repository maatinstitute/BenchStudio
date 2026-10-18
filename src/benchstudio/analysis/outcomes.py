"""Outcome provenance and authoritative-scorer audits."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

OutcomeSource = Literal["official", "declared", "supplementary"]


@dataclass(frozen=True)
class OutcomeRecord:
    attempt_id: str
    success: bool | None
    source: OutcomeSource
    evaluator_id: str | None = None
    evaluator_revision: str | None = None
    source_artifact_sha256: str | None = None
    authoritative: bool = False


@dataclass(frozen=True)
class OutcomeProvenanceAudit:
    records: int
    complete_outcomes: int
    authoritative_records: int
    supplementary_records: int
    valid: bool
    authoritative_scorer_declared: bool
    issues: tuple[str, ...]

    @property
    def outcome_present(self) -> bool:
        return self.complete_outcomes == self.records and self.records > 0


def validate_outcome_record(record: OutcomeRecord) -> list[str]:
    issues: list[str] = []
    if not record.attempt_id:
        issues.append("attempt_id is required")
    if record.source not in {"official", "declared", "supplementary"}:
        issues.append("source must be official, declared, or supplementary")
    if record.source in {"official", "declared"}:
        if not record.evaluator_id:
            issues.append("authoritative outcomes require evaluator_id")
        if not record.evaluator_revision:
            issues.append("authoritative outcomes require evaluator_revision")
        if not record.authoritative:
            issues.append("authoritative outcomes must set authoritative=true")
    if record.source == "supplementary" and record.authoritative:
        issues.append("supplementary outcomes cannot be authoritative")
    if (
        record.source_artifact_sha256 is not None
        and re.fullmatch(r"sha256:[0-9a-f]{64}", record.source_artifact_sha256) is None
    ):
        issues.append("source_artifact_sha256 must be sha256:<lowercase digest>")
    return issues


def audit_outcome_provenance(records: list[OutcomeRecord]) -> OutcomeProvenanceAudit:
    issues: list[str] = []
    seen: set[str] = set()
    complete = authoritative = supplementary = 0
    for record in records:
        if record.attempt_id in seen:
            issues.append(f"duplicate outcome attempt_id: {record.attempt_id}")
        seen.add(record.attempt_id)
        issues.extend(f"{record.attempt_id}: {issue}" for issue in validate_outcome_record(record))
        if record.success is not None:
            complete += 1
        if record.authoritative:
            authoritative += 1
        if record.source == "supplementary":
            supplementary += 1
    if records and complete != len(records):
        issues.append("some outcomes are missing")
    return OutcomeProvenanceAudit(
        records=len(records),
        complete_outcomes=complete,
        authoritative_records=authoritative,
        supplementary_records=supplementary,
        valid=not issues,
        authoritative_scorer_declared=authoritative == len(records)
        and bool(records)
        and not issues,
        issues=tuple(issues),
    )
