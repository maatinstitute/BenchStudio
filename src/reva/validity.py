from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
ContaminationStatus = Literal["not_assessed", "clear", "flagged"]
MetricStability = Literal["not_assessed", "stable", "unstable"]
MetricScope = Literal["official", "supplementary", "both"]


@dataclass(frozen=True)
class BenchmarkValidityRecord:
    """Frozen metadata needed to interpret a benchmark score."""

    task_definition_revision: str
    dataset_lineage_digest: str
    contamination_review: ContaminationStatus
    excluded_attempt_ids: tuple[str, ...]
    early_termination_policy: str
    metric_revision: str
    metric_scope: MetricScope
    metric_stability: MetricStability

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, field: str = "validity"):
        if not isinstance(value, Mapping):
            raise ValueError(f"{field} must be a mapping")
        task_revision = value.get("task_definition_revision")
        lineage = value.get("dataset_lineage_digest")
        metric_revision = value.get("metric_revision")
        for name, item in (
            ("task_definition_revision", task_revision),
            ("metric_revision", metric_revision),
        ):
            if not isinstance(item, str) or not item:
                raise ValueError(f"{field}.{name} must be a non-empty string")
        if not isinstance(lineage, str) or _DIGEST.fullmatch(lineage) is None:
            raise ValueError(f"{field}.dataset_lineage_digest must be sha256:<lowercase digest>")
        contamination = value.get("contamination_review", "not_assessed")
        if contamination not in {"not_assessed", "clear", "flagged"}:
            raise ValueError(f"{field}.contamination_review is invalid")
        stability = value.get("metric_stability", "not_assessed")
        if stability not in {"not_assessed", "stable", "unstable"}:
            raise ValueError(f"{field}.metric_stability is invalid")
        scope = value.get("metric_scope", "supplementary")
        if scope not in {"official", "supplementary", "both"}:
            raise ValueError(f"{field}.metric_scope is invalid")
        termination = value.get("early_termination_policy")
        if not isinstance(termination, str) or not termination:
            raise ValueError(f"{field}.early_termination_policy must be a non-empty string")
        excluded = value.get("excluded_attempt_ids", ())
        if not isinstance(excluded, (list, tuple)) or not all(
            isinstance(item, str) and item for item in excluded
        ):
            raise ValueError(f"{field}.excluded_attempt_ids must contain non-empty strings")
        return cls(
            task_revision,
            lineage,
            contamination,
            tuple(excluded),
            termination,
            metric_revision,
            scope,
            stability,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_definition_revision": self.task_definition_revision,
            "dataset_lineage_digest": self.dataset_lineage_digest,
            "contamination_review": self.contamination_review,
            "excluded_attempt_ids": list(self.excluded_attempt_ids),
            "early_termination_policy": self.early_termination_policy,
            "metric_revision": self.metric_revision,
            "metric_scope": self.metric_scope,
            "metric_stability": self.metric_stability,
        }


@dataclass(frozen=True)
class BenchmarkValidityAudit:
    valid: bool
    issues: tuple[str, ...]
    excluded_attempt_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": list(self.issues),
            "excluded_attempt_ids": list(self.excluded_attempt_ids),
        }


def audit_benchmark_validity(
    record: BenchmarkValidityRecord, planned_attempt_ids: set[str] | None = None
) -> BenchmarkValidityAudit:
    issues: list[str] = []
    if record.contamination_review != "clear":
        issues.append(f"contamination review is {record.contamination_review}")
    if record.metric_stability != "stable":
        issues.append(f"metric stability is {record.metric_stability}")
    if len(set(record.excluded_attempt_ids)) != len(record.excluded_attempt_ids):
        issues.append("excluded_attempt_ids contains duplicates")
    if planned_attempt_ids is not None:
        unknown = sorted(set(record.excluded_attempt_ids) - planned_attempt_ids)
        if unknown:
            issues.append("excluded_attempt_ids contains unknown attempts: " + ", ".join(unknown))
    return BenchmarkValidityAudit(not issues, tuple(issues), record.excluded_attempt_ids)
