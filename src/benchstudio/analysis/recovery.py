from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..campaigns.counterfactual import FrozenCounterfactualPlan
from .paired import clopper_pearson_interval


@dataclass(frozen=True)
class RecoverySummary:
    scheduled_pairs: int
    matched_pairs: int
    missing_pairs: int
    nominal_success_rate: float | None
    intervention_success_rate: float | None
    recovery_rate: float | None
    mean_recovery_time_ms: float | None
    issues: tuple[str, ...]
    recovery_confidence_interval: tuple[float, float] | None = None
    lineage_valid: bool | None = None
    lineage_issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "benchstudio_recovery_report_v1",
            "scheduled_pairs": self.scheduled_pairs,
            "matched_pairs": self.matched_pairs,
            "missing_pairs": self.missing_pairs,
            "nominal_success_rate": self.nominal_success_rate,
            "intervention_success_rate": self.intervention_success_rate,
            "recovery_rate": self.recovery_rate,
            "mean_recovery_time_ms": self.mean_recovery_time_ms,
            "recovery_confidence_interval": (
                list(self.recovery_confidence_interval)
                if self.recovery_confidence_interval is not None
                else None
            ),
            "issues": list(self.issues),
            "lineage_valid": self.lineage_valid,
            "lineage_issues": list(self.lineage_issues),
        }


def load_recovery_records(path: Path) -> list[dict[str, Any]]:
    """Load counterfactual branch records from JSON, JSONL, or NDJSON."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        values = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        values = json.loads(text)
        if isinstance(values, dict):
            values = values.get("records")
    if not isinstance(values, list) or not all(isinstance(value, dict) for value in values):
        raise ValueError("recovery records must be a JSON array or {records: [...]} mapping")
    return values


def write_recovery_report(report: RecoverySummary, path: Path) -> None:
    """Write deterministic recovery evidence without imputing missing branches."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class CounterfactualOutcomeAudit:
    scheduled_branches: int
    recorded_branches: int
    missing_branch_attempt_ids: tuple[str, ...]
    unknown_branch_attempt_ids: tuple[str, ...]
    duplicate_branch_attempt_ids: tuple[str, ...]
    lineage_issues: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return (
            not (
                self.missing_branch_attempt_ids
                or self.unknown_branch_attempt_ids
                or self.duplicate_branch_attempt_ids
                or self.lineage_issues
            )
            and self.recorded_branches == self.scheduled_branches
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheduled_branches": self.scheduled_branches,
            "recorded_branches": self.recorded_branches,
            "missing_branch_attempt_ids": list(self.missing_branch_attempt_ids),
            "unknown_branch_attempt_ids": list(self.unknown_branch_attempt_ids),
            "duplicate_branch_attempt_ids": list(self.duplicate_branch_attempt_ids),
            "lineage_issues": list(self.lineage_issues),
            "complete": self.complete,
        }


def audit_counterfactual_outcomes(
    plan: FrozenCounterfactualPlan, records: list[dict[str, Any]]
) -> CounterfactualOutcomeAudit:
    """Verify observed branches against a frozen counterfactual plan."""
    expected: dict[str, tuple[str, str, int, str]] = {}
    for pair in plan.pairs:
        for cell in (pair.nominal, pair.intervention):
            expected[cell.branch_attempt_id] = (
                cell.pair_id,
                cell.branch,
                cell.intervention.transition_index,
                cell.intervention.intervention_id,
            )
    occurrences: dict[str, int] = {}
    unknown: set[str] = set()
    lineage: list[str] = []
    for index, record in enumerate(records):
        branch_attempt_id = record.get("branch_attempt_id")
        if not isinstance(branch_attempt_id, str) or not branch_attempt_id:
            lineage.append(f"record {index}: missing branch_attempt_id")
            continue
        occurrences[branch_attempt_id] = occurrences.get(branch_attempt_id, 0) + 1
        expected_row = expected.get(branch_attempt_id)
        if expected_row is None:
            unknown.add(branch_attempt_id)
            continue
        success = record.get("success")
        if success is not None and not isinstance(success, bool):
            lineage.append(f"{branch_attempt_id}: success must be boolean or None")
        recovery_time = record.get("recovery_time_ms")
        if recovery_time is not None and (
            isinstance(recovery_time, bool)
            or not isinstance(recovery_time, (int, float))
            or not math.isfinite(float(recovery_time))
            or recovery_time < 0
        ):
            lineage.append(f"{branch_attempt_id}: recovery_time_ms must be finite and non-negative")
        pair_id, branch, transition_index, intervention_id = expected_row
        if record.get("pair_id") != pair_id:
            lineage.append(f"{branch_attempt_id}: pair_id does not match frozen plan")
        if record.get("branch") != branch:
            lineage.append(f"{branch_attempt_id}: branch does not match frozen plan")
        if record.get("transition_index") != transition_index:
            lineage.append(f"{branch_attempt_id}: transition_index does not match frozen plan")
        if record.get("intervention_id") != intervention_id:
            lineage.append(f"{branch_attempt_id}: intervention_id does not match frozen plan")
    duplicates = tuple(sorted(item for item, count in occurrences.items() if count > 1))
    missing = tuple(sorted(set(expected) - occurrences.keys()))
    return CounterfactualOutcomeAudit(
        len(expected),
        len(records),
        missing,
        tuple(sorted(unknown)),
        duplicates,
        tuple(lineage),
    )


def summarize_recovery_outcomes(records: list[dict[str, Any]]) -> RecoverySummary:
    """Summarize paired nominal/intervention outcomes without imputing branches.

    Records must contain ``pair_id``, ``branch`` (``nominal`` or
    ``intervention``), and a boolean ``success``. Recovery is reported as
    intervention success among matched pairs; it is not inferred from a
    missing nominal or intervention branch.
    """
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    issues: list[str] = []
    for index, record in enumerate(records):
        pair_id = record.get("pair_id")
        branch = record.get("branch")
        if not isinstance(pair_id, str) or not pair_id:
            issues.append(f"record {index}: missing pair_id")
            continue
        if branch not in {"nominal", "intervention"}:
            issues.append(f"record {index}: invalid branch")
            continue
        if branch in grouped.setdefault(pair_id, {}):
            issues.append(f"duplicate {branch} branch for pair {pair_id}")
            continue
        grouped[pair_id][branch] = record
    matched = [
        branches
        for branches in grouped.values()
        if "nominal" in branches and "intervention" in branches
    ]
    missing = len(grouped) - len(matched)
    if missing:
        issues.append("some nominal/intervention branches are missing")
    complete = [
        branches
        for branches in matched
        if isinstance(branches["nominal"].get("success"), bool)
        and isinstance(branches["intervention"].get("success"), bool)
    ]
    if len(complete) < len(matched):
        issues.append("some matched branches have missing outcomes")
    if not complete:
        return RecoverySummary(
            len(grouped),
            0,
            missing,
            None,
            None,
            None,
            None,
            tuple(issues + ["no complete recovery pairs"]),
            None,
        )
    recovery_times = [
        float(branches["intervention"]["recovery_time_ms"])
        for branches in complete
        if isinstance(branches["intervention"].get("recovery_time_ms"), (int, float))
        and math.isfinite(float(branches["intervention"]["recovery_time_ms"]))
    ]
    nominal_rate = sum(branches["nominal"]["success"] for branches in complete) / len(complete)
    intervention_rate = sum(branches["intervention"]["success"] for branches in complete) / len(
        complete
    )
    return RecoverySummary(
        len(grouped),
        len(complete),
        missing + len(matched) - len(complete),
        nominal_rate,
        intervention_rate,
        intervention_rate,
        sum(recovery_times) / len(recovery_times) if recovery_times else None,
        tuple(issues),
        clopper_pearson_interval(
            sum(branches["intervention"]["success"] for branches in complete),
            len(complete),
        ),
    )
