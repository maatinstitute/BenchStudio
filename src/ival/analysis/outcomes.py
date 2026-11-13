"""Outcome provenance and authoritative-scorer audits."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "OutcomeRecord":
        if not isinstance(value, dict):
            raise ValueError("outcome record must be a mapping")
        fields = {
            "attempt_id",
            "success",
            "source",
            "evaluator_id",
            "evaluator_revision",
            "source_artifact_sha256",
            "authoritative",
        }
        unknown = set(value) - fields
        if unknown:
            raise ValueError(f"unknown outcome fields: {sorted(unknown)}")
        required = fields - {
            "evaluator_id",
            "evaluator_revision",
            "source_artifact_sha256",
            "authoritative",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise ValueError(f"missing outcome fields: {missing}")
        return cls(
            attempt_id=value["attempt_id"],
            success=value["success"],
            source=value["source"],
            evaluator_id=value.get("evaluator_id"),
            evaluator_revision=value.get("evaluator_revision"),
            source_artifact_sha256=value.get("source_artifact_sha256"),
            authoritative=value.get("authoritative", False),
        )


class OutcomeLedger:
    """Append-only, plan-bound persistence for scorer outcome records."""

    def __init__(
        self,
        path: Path,
        *,
        attempt_ids: set[str] | frozenset[str] | None = None,
        plan_digest_sha256: str | None = None,
    ) -> None:
        self.path = path
        self.attempt_ids = set(attempt_ids) if attempt_ids is not None else None
        if plan_digest_sha256 is not None and not _is_hex_digest(plan_digest_sha256):
            raise ValueError("plan_digest_sha256 must be a lowercase SHA-256 hex digest")
        self.plan_digest_sha256 = plan_digest_sha256
        self._records: list[OutcomeRecord] = []
        self._seen: set[str] = set()
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                envelope = json.loads(line)
                if not isinstance(envelope, dict):
                    raise ValueError("outcome ledger envelope must be a mapping")
                if envelope.get("schema") != "ival.outcome.v1":
                    raise ValueError("unsupported outcome ledger schema")
                envelope_digest = envelope.get("plan_digest_sha256")
                if envelope_digest is not None and not _is_hex_digest(envelope_digest):
                    raise ValueError("outcome ledger plan digest is invalid")
                if plan_digest_sha256 is not None and envelope_digest != plan_digest_sha256:
                    raise ValueError("outcome record does not match frozen plan digest")
                record_payload = envelope.get("record")
                if not isinstance(record_payload, dict):
                    raise ValueError("outcome ledger record must be a mapping")
                self._load(OutcomeRecord.from_dict(record_payload))
        path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def records(self) -> tuple[OutcomeRecord, ...]:
        return tuple(self._records)

    def append(self, record: OutcomeRecord) -> None:
        self._load(record)
        envelope = {
            "schema": "ival.outcome.v1",
            "plan_digest_sha256": self.plan_digest_sha256,
            "record": record.to_dict(),
        }
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(envelope, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            self._records.pop()
            self._seen.remove(record.attempt_id)
            raise

    def _load(self, record: OutcomeRecord) -> None:
        issues = validate_outcome_record(record)
        if issues:
            raise ValueError("invalid outcome record: " + "; ".join(issues))
        if self.attempt_ids is not None and record.attempt_id not in self.attempt_ids:
            raise ValueError(f"outcome attempt is outside frozen plan: {record.attempt_id}")
        if record.attempt_id in self._seen:
            raise ValueError(f"duplicate outcome attempt_id: {record.attempt_id}")
        self._seen.add(record.attempt_id)
        self._records.append(record)


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "complete_outcomes": self.complete_outcomes,
            "authoritative_records": self.authoritative_records,
            "supplementary_records": self.supplementary_records,
            "valid": self.valid,
            "authoritative_scorer_declared": self.authoritative_scorer_declared,
            "outcome_present": self.outcome_present,
            "issues": list(self.issues),
        }


def validate_outcome_record(record: OutcomeRecord) -> list[str]:
    issues: list[str] = []
    if not isinstance(record.attempt_id, str) or not record.attempt_id:
        issues.append("attempt_id must be a non-empty string")
    if record.success is not None and not isinstance(record.success, bool):
        issues.append("success must be boolean or None")
    if not isinstance(record.source, str) or record.source not in {
        "official",
        "declared",
        "supplementary",
    }:
        issues.append("source must be official, declared, or supplementary")
    if not isinstance(record.authoritative, bool):
        issues.append("authoritative must be boolean")
    if record.source in {"official", "declared"}:
        if not isinstance(record.evaluator_id, str) or not record.evaluator_id:
            issues.append("authoritative outcomes require evaluator_id")
        if not isinstance(record.evaluator_revision, str) or not record.evaluator_revision:
            issues.append("authoritative outcomes require evaluator_revision")
        if not record.authoritative:
            issues.append("authoritative outcomes must set authoritative=true")
    if record.source == "supplementary" and record.authoritative:
        issues.append("supplementary outcomes cannot be authoritative")
    if record.source_artifact_sha256 is not None and (
        not isinstance(record.source_artifact_sha256, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", record.source_artifact_sha256) is None
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


def _is_hex_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
