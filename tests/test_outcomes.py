from __future__ import annotations

from benchstudio.analysis import (
    OutcomeRecord,
    audit_outcome_provenance,
    validate_outcome_record,
)


def test_authoritative_outcome_requires_declared_scorer_identity():
    record = OutcomeRecord(
        "attempt-1", True, "official", "table30-scorer", "rev-4", authoritative=True
    )
    assert validate_outcome_record(record) == []
    audit = audit_outcome_provenance([record])
    assert audit.valid
    assert audit.authoritative_scorer_declared


def test_supplementary_outcomes_cannot_be_used_as_authoritative_scores():
    record = OutcomeRecord("attempt-1", True, "supplementary", "benchstudio-diagnostic")
    audit = audit_outcome_provenance([record])
    assert audit.valid
    assert not audit.authoritative_scorer_declared


def test_missing_outcome_and_bad_artifact_digest_are_preserved_as_issues():
    record = OutcomeRecord(
        "attempt-1", None, "declared", "scorer", "rev", "sha256:not-a-digest", True
    )
    audit = audit_outcome_provenance([record])
    assert audit.valid is False
    assert "some outcomes are missing" in audit.issues
    assert any("source_artifact_sha256" in issue for issue in audit.issues)
