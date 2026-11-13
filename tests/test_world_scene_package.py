from datetime import datetime, timezone

from ival.scenarios.world_scene_package import (
    WorldInterfaceSpec,
    WorldScenePackageManifest,
    WorldScenePackageRegistry,
    WorldSnapshot,
    validate_world_scene_package,
    world_scene_package_digest,
)


def _manifest():
    return WorldScenePackageManifest(
        schema_version="1.0.0", package_id="scene-a", version="1", title="Scene A",
        created_at=datetime.now(timezone.utc).isoformat(),
        interface=WorldInterfaceSpec(("rgb",), "joint_position", 20, "base_link"),
        world_snapshot=WorldSnapshot("<robot/>", {"joint": 0.0}, scenario_duration_ms=1000),
        provenance={"owner": "IVal", "tags": ["demo", "scene"]},
    )


def test_world_scene_package_digest_and_validation_are_deterministic():
    manifest = _manifest()
    assert validate_world_scene_package(manifest) == []
    assert world_scene_package_digest(manifest) == world_scene_package_digest(
        WorldScenePackageManifest.from_dict(manifest.to_dict())
    )


def test_registry_publishes_and_reloads_version(tmp_path):
    registry = WorldScenePackageRegistry(tmp_path / "world-registry.json")
    record = registry.publish(_manifest())
    loaded = registry.get_version("scene-a", "1")
    assert loaded.digest_sha256 == record.digest_sha256
    assert loaded.manifest.package_id == "scene-a"


def test_registry_lists_latest_versions_with_trust_and_filters(tmp_path):
    registry = WorldScenePackageRegistry(tmp_path / "world-registry.json")
    registry.publish(_manifest())
    entries = registry.list_packages(query="scene", owner="ival", tags=["demo"])
    assert len(entries) == 1
    assert entries[0].trust_level == "metadata_only"
    assert entries[0].runtime_targets == ()


def test_registry_reports_capabilities_and_validation_warnings(tmp_path):
    registry = WorldScenePackageRegistry(tmp_path / "world-registry.json")
    validation = registry.validate(_manifest())
    capabilities = registry.get_capabilities()
    assert validation.valid is True
    assert any("No runtime_targets declared" in warning for warning in validation.warnings)
    assert capabilities.available is True
    assert capabilities.can_publish is True


def test_registry_rejects_static_scene_with_nonzero_time(tmp_path):
    registry = WorldScenePackageRegistry(tmp_path / "world-registry.json")
    manifest = _manifest()
    # Constructing through the dataclass keeps the invalid state available for
    # the registry validator, matching the source service's validation stage.
    invalid = WorldScenePackageManifest(
        **{**manifest.__dict__, "world_snapshot": WorldSnapshot("<robot/>", {"joint": 0.0}, scenario_time_ms=100)}
    )
    result = registry.validate(invalid)
    assert result.valid is False
    assert "scenario_time_ms must be between zero and scenario_duration_ms" in result.errors
