from importlib import import_module
from unittest.mock import patch

import pytest

import benchstudio as bs
from benchstudio.analysis.campaign_audit import audit_campaign
from benchstudio.analysis.claims import ClaimType
from benchstudio.campaigns.frozen_plan import CampaignPlanner


def test_campaign_audit_pipeline_uses_offline_directory_audit(tmp_path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    expected = object()

    pipeline_module = import_module("benchstudio.pipeline")
    with patch.object(pipeline_module, "audit_campaign_directory", return_value=expected) as audit:
        review = bs.pipeline("campaign-audit", claim_type=ClaimType.PAIRED_COMPARISON)
        result = review(campaign)

    assert result is expected
    audit.assert_called_once_with(campaign, claim_type=ClaimType.PAIRED_COMPARISON)


def test_campaign_audit_pipeline_rejects_missing_and_non_directory_sources(tmp_path):
    review = bs.pipeline("campaign-audit")
    with pytest.raises(FileNotFoundError, match="does not exist"):
        review(tmp_path / "missing")
    archive = tmp_path / "campaign.zip"
    archive.write_bytes(b"not extracted")
    with pytest.raises(ValueError, match="expects a campaign directory"):
        review(archive)


def test_pipeline_factory_lists_supported_task():
    with pytest.raises(ValueError, match="campaign-audit"):
        bs.pipeline("policy-loading")


def test_campaign_audit_has_a_concise_summary():
    plan = CampaignPlanner(
        run_id="summary", scenario_id="task", conditions=[{"variant": "A"}], seeds=[7]
    ).freeze()
    attempt_id = plan.attempts[0].key.attempt_id
    report = audit_campaign(
        plan,
        [{"attempt_id": attempt_id, "status": "completed", "evidence_verified": True}],
        claim_type=ClaimType.SINGLE_RUN_OUTCOME,
        evidence={"authoritative_scorer_declared": True},
    )

    assert report.summary() == (
        "Campaign audit complete: 1/1 attempts; 0 missing, 0 duplicates, 0 unknown; "
        "evidence verified; claim supported."
    )
