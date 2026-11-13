import hashlib

from benchstudio.scenarios.world_rollout import (
    WorldRolloutCheckerProfile,
    WorldRolloutModuleSpec,
    build_world_rollout_campaign,
    import_world_rollout_results,
)
from benchstudio.scenarios.world_scene_package import WorldInterfaceSpec, WorldScenePackageManifest, WorldSnapshot


def _package():
    return WorldScenePackageManifest(
        schema_version="1.0.0", package_id="demo-world", version="1", title="Demo",
        created_at="2026-01-01T00:00:00+00:00",
        interface=WorldInterfaceSpec(("state",), "joint_position", 50, "world"),
        world_snapshot=WorldSnapshot("<robot/>", scenario_duration_ms=100),
    )


def test_campaign_binds_package_and_checker_digests_and_import_counts():
    profile = WorldRolloutCheckerProfile(
        profile_id="checker", target_id="robot",
        modules=(WorldRolloutModuleSpec("stop", "tier1", "hardware_stop"),),
    )
    campaign = build_world_rollout_campaign(_package(), profile)
    trace = '{"t_ms":10,"stream":"state"}\n'
    decisions = '{"decision":"stop","rule_id":"hardware_stop"}\n{"decision":"warn","rule_id":"uncertain"}\n'
    campaign = type(campaign)(**{**campaign.__dict__, "artifacts": campaign.artifacts + (
        type(campaign.artifacts[0])("trace_ndjson", "trace.ndjson", hashlib.sha256(trace.encode()).hexdigest()),
        type(campaign.artifacts[0])("decisions_ndjson", "decisions.ndjson", hashlib.sha256(decisions.encode()).hexdigest()),
    )})
    imported = import_world_rollout_results(campaign, trace_ndjson=trace, decisions_ndjson=decisions)
    assert imported.counts == {"trace_record_count": 1, "decision_count": 2, "reject_count": 0, "warn_count": 1, "stop_count": 1, "escalation_count": 0}


def test_import_rejects_digest_mismatch():
    profile = WorldRolloutCheckerProfile("checker", "robot")
    campaign = build_world_rollout_campaign(_package(), profile)
    artifact = type(campaign.artifacts[0])("trace_ndjson", "trace.ndjson", "0" * 64)
    campaign = type(campaign)(**{**campaign.__dict__, "artifacts": campaign.artifacts + (artifact,)})
    try:
        import_world_rollout_results(campaign, trace_ndjson='{"t_ms":0}\n')
    except ValueError as exc:
        assert "digest mismatch" in str(exc)
    else:
        raise AssertionError("expected digest mismatch")
