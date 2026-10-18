from __future__ import annotations

from benchstudio import ModelCapabilityProfile
from benchstudio.analysis import (
    ClaimType,
    ResourceBudget,
    audit_resources,
    estimate_transfer_gap,
    validate_claim,
)


def test_claim_validation_does_not_infer_transfer_from_simulation():
    decision = validate_claim(
        ClaimType.REAL_WORLD_TRANSFER,
        {
            "paired_conditions": True,
            "semantic_match": True,
            "simulation_evidence": True,
            "physical_evidence": False,
            "transfer_protocol": False,
        },
    )
    assert decision.status == "unsupported"
    assert "missing prerequisite: physical_evidence" in decision.reasons


def test_single_outcome_can_be_qualified_when_completion_is_incomplete():
    decision = validate_claim(
        ClaimType.SINGLE_RUN_OUTCOME,
        {
            "outcome_present": True,
            "authoritative_scorer_declared": False,
            "trusted_artifacts": True,
        },
    )
    assert decision.status == "qualified"


def test_transfer_gap_preserves_missingness_and_resource_violations():
    gap = estimate_transfer_gap([True, False, None], [True, True, False])
    assert gap.matched_pairs == 2
    assert gap.valid is False
    audit = audit_resources(
        calls=4,
        wall_time_ms=110,
        compute_time_ms=20,
        budget=ResourceBudget(max_inference_calls=3, max_wall_time_ms=100),
    )
    assert set(audit.violations) == {"inference_call_budget_exceeded", "wall_time_budget_exceeded"}


def test_model_capability_profile_declares_supported_metrics():
    profile = ModelCapabilityProfile(
        "mock-vla", "vla", ("rgb", "proprioception"), "joint_position", True, True, ("success",)
    )
    assert profile.supports("success")
    assert not profile.supports("latent_quality")
