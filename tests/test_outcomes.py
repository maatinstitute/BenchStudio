from __future__ import annotations

from benchstudio.analysis import (
    OutcomeLedger,
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


def test_outcome_schema_rejects_non_boolean_runtime_fields():
    record = OutcomeRecord(17, "true", "official", "scorer", "rev", authoritative="yes")
    issues = validate_outcome_record(record)
    assert "attempt_id must be a non-empty string" in issues
    assert "success must be boolean or None" in issues
    assert "authoritative must be boolean" in issues
    audit = audit_outcome_provenance([record])
    assert audit.valid is False


def test_outcome_loader_reports_missing_required_fields():
    import pytest

    with pytest.raises(ValueError, match="missing outcome fields"):
        OutcomeRecord.from_dict({"attempt_id": "attempt-1", "success": True})


def test_outcome_ledger_round_trips_and_binds_to_frozen_attempts(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    ledger = OutcomeLedger(path, attempt_ids={"attempt-1"}, plan_digest_sha256="a" * 64)
    record = OutcomeRecord("attempt-1", True, "official", "scorer", "rev-1", authoritative=True)
    ledger.append(record)
    reopened = OutcomeLedger(path, attempt_ids={"attempt-1"}, plan_digest_sha256="a" * 64)
    assert reopened.records == (record,)
    with __import__("pytest").raises(ValueError, match="duplicate"):
        reopened.append(record)
    with __import__("pytest").raises(ValueError, match="outside frozen plan"):
        reopened.append(OutcomeRecord("attempt-2", True, "supplementary"))


def test_outcome_ledger_rejects_plan_digest_mismatch(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    ledger = OutcomeLedger(path, attempt_ids={"attempt-1"}, plan_digest_sha256="a" * 64)
    ledger.append(OutcomeRecord("attempt-1", True, "official", "scorer", "rev", authoritative=True))
    with __import__("pytest").raises(ValueError, match="frozen plan digest"):
        OutcomeLedger(path, attempt_ids={"attempt-1"}, plan_digest_sha256="b" * 64)


def test_outcome_ledger_rejects_malformed_envelopes(tmp_path):
    import pytest

    path = tmp_path / "outcomes.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="envelope must be a mapping"):
        OutcomeLedger(path, plan_digest_sha256="a" * 64)


def test_outcome_ledger_rejects_invalid_plan_digest():
    import pytest

    with pytest.raises(ValueError, match="plan_digest_sha256 must be"):
        OutcomeLedger(__import__("pathlib").Path("outcomes.jsonl"), plan_digest_sha256="bad")
