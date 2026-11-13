from __future__ import annotations

import pytest

from ival.validity import BenchmarkValidityRecord, audit_benchmark_validity


def _record(**overrides):
    value = {
        "task_definition_revision": "task-v1",
        "dataset_lineage_digest": "sha256:" + "1" * 64,
        "contamination_review": "clear",
        "excluded_attempt_ids": ["attempt-000001"],
        "early_termination_policy": "success_allowed",
        "metric_revision": "metric-v1",
        "metric_scope": "official",
        "metric_stability": "stable",
    }
    value.update(overrides)
    return BenchmarkValidityRecord.from_mapping(value)


def test_benchmark_validity_audit_accepts_explicit_clean_record():
    audit = audit_benchmark_validity(_record(), {"attempt-000000", "attempt-000001"})
    assert audit.valid is True
    assert audit.to_dict()["excluded_attempt_ids"] == ["attempt-000001"]


def test_benchmark_validity_audit_rejects_unassessed_or_unknown_records():
    audit = audit_benchmark_validity(
        _record(contamination_review="not_assessed", excluded_attempt_ids=["unknown"]),
        {"attempt-000000"},
    )
    assert audit.valid is False
    assert "contamination review is not_assessed" in audit.issues
    assert any("unknown attempts" in issue for issue in audit.issues)


def test_benchmark_validity_rejects_invalid_lineage_digest():
    with pytest.raises(ValueError, match="dataset_lineage_digest"):
        _record(dataset_lineage_digest="bad")
