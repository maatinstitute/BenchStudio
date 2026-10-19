from datetime import datetime, timezone

from benchstudio.scenarios.world_scene_package import (
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
