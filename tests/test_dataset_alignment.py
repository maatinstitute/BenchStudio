from __future__ import annotations

from benchstudio.conformance import (
    AlignmentEndpoint,
    AlignmentJointRule,
    AlignmentMapping,
    AlignmentQuery,
    DatasetAlignmentInput,
    DatasetAlignmentRegistry,
    EmbodimentResolveRequest,
)


def test_resolve_reuses_matching_injected_fingerprint(tmp_path):
    registry = DatasetAlignmentRegistry(
        tmp_path / "alignment.json", fingerprint_resolver=lambda _: "fp-v1"
    )
    first = registry.resolve_embodiment(
        EmbodimentResolveRequest(urdf_xml="<robot/>", robot_type="demo")
    )
    second = registry.resolve_embodiment(
        EmbodimentResolveRequest(urdf_xml="<renamed/>", robot_type="other")
    )
    assert first.matched_existing is False
    assert second.matched_existing is True
    assert first.embodiment.embodiment_id == second.embodiment.embodiment_id


def test_mapping_roundtrip_filter_and_representation_validation(tmp_path):
    registry = DatasetAlignmentRegistry(tmp_path / "alignment.json")
    saved = registry.upsert_mapping(
        AlignmentMapping(
            source=AlignmentEndpoint("unknown:abc", "rep:indexed"),
            target=AlignmentEndpoint("robot:v1", "rep:semantic"),
            joint_rules=(AlignmentJointRule("motor_0", "arm.shoulder_pan"),),
        )
    )
    assert saved.mapping_id is not None
    assert len(registry.list_mappings(AlignmentQuery(target_representation_id="rep:semantic"))) == 1
    invalid = registry.validate_datasets(
        [DatasetAlignmentInput("demo", "unknown:abc", "rep:indexed")],
        required_representation_id="rep:semantic",
    )
    assert invalid.valid is True
    unnamed = registry.validate_datasets(
        [DatasetAlignmentInput("demo", "unknown:abc", "rep:semantic", "unnamed")],
        required_representation_id="rep:semantic",
    )
    assert unnamed.valid is False
    assert any("unnamed joints" in issue for issue in unnamed.errors)


def test_unknown_embodiment_is_stable_without_fingerprint(tmp_path):
    registry = DatasetAlignmentRegistry(tmp_path / "alignment.json")
    first = registry.resolve_embodiment(
        EmbodimentResolveRequest(robot_type="custom", base_frame="base")
    )
    second = registry.resolve_embodiment(
        EmbodimentResolveRequest(robot_type="custom", base_frame="base")
    )
    assert first.embodiment.embodiment_id.startswith("unknown:")
    assert second.matched_existing is False
    assert second.embodiment.embodiment_id == first.embodiment.embodiment_id
