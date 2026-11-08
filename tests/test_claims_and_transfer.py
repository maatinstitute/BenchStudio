from __future__ import annotations

from benchstudio.contracts import ModelCapabilityProfile
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


def test_claim_validation_rejects_truthy_non_boolean_evidence():
    decision = validate_claim(
        ClaimType.SINGLE_RUN_OUTCOME,
        {
            "outcome_present": True,
            "authoritative_scorer_declared": "true",
            "trusted_artifacts": 1,
            "attempts_complete": True,
        },
    )
    assert decision.status == "qualified"
    assert "missing prerequisite: authoritative_scorer_declared" in decision.reasons
    assert "missing prerequisite: trusted_artifacts" in decision.reasons


def test_transfer_claim_requires_scored_outcomes_and_trusted_evidence():
    decision = validate_claim(
        ClaimType.REAL_WORLD_TRANSFER,
        {
            "paired_conditions": True,
            "semantic_match": True,
            "simulation_evidence": True,
            "physical_evidence": True,
            "transfer_protocol": True,
            "attempts_complete": True,
        },
    )
    assert decision.status == "unsupported"
    assert "missing prerequisite: outcome_present" in decision.reasons
    assert "missing prerequisite: authoritative_scorer_declared" in decision.reasons
    assert "missing prerequisite: trusted_artifacts" in decision.reasons


def test_claim_validation_rejects_unknown_claim_type():
    import pytest

    with pytest.raises(ValueError, match="unsupported claim type"):
        validate_claim("invented", {})


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
    assert profile.validate() == []


def test_model_capability_profile_declares_runtime_and_timing_contract():
    profile = ModelCapabilityProfile(
        "planner",
        "planner",
        ("state",),
        "trajectory",
        True,
        False,
        ("success",),
        input_contract="worldepisode.observation.v1",
        inference_granularity="trajectory",
        runtime_controls=("horizon",),
        memory_bytes=1024,
        timing_signals=("host_monotonic", "gpu_event"),
        supports_async=True,
        supports_variable_action_horizon=True,
    )
    assert profile.validate() == []
