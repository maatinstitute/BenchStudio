from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class SignalSpec:
    name: str
    signal: Literal["joint_position", "joint_velocity", "ee_pose", "gripper"]
    units: str
    labels: tuple[str, ...]
    reference_frame: str | None = None


@dataclass(frozen=True)
class MappingRule:
    source_label: str
    target_label: str
    scale: float = 1.0
    offset: float = 0.0
    invert: bool = False

    def apply(self, value: float) -> float:
        mapped = value * self.scale + self.offset
        return -mapped if self.invert else mapped


@dataclass(frozen=True)
class EmbodimentRef:
    embodiment_id: str
    kinematic_fingerprint: str | None = None
    urdf_sha256: str | None = None
    srdf_sha256: str | None = None
    robot_type: str | None = None
    base_frame: str | None = None
    ee_frame: str | None = None


@dataclass(frozen=True)
class RepresentationSignalSpec:
    signal_type: str
    units: str
    ordering: str
    joints: tuple[str, ...] = ()
    dt_s: float | None = None
    base_frame: str | None = None


@dataclass(frozen=True)
class RepresentationSpec:
    representation_id: str
    state: RepresentationSignalSpec
    action: RepresentationSignalSpec
    version: str = "v1"


@dataclass(frozen=True)
class MappingEndpoint:
    embodiment_id: str
    representation_id: str


@dataclass(frozen=True)
class MappingSpec:
    source: MappingEndpoint
    target: MappingEndpoint
    rules: tuple[MappingRule, ...] = field(default_factory=tuple)
    mapping_id: str | None = None

    def content_id(self) -> str:
        payload = {
            "source": self.source.__dict__,
            "target": self.target.__dict__,
            "rules": [rule.__dict__ for rule in self.rules],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def validate_mapping(
    source: SignalSpec, target: SignalSpec, rules: tuple[MappingRule, ...]
) -> list[str]:
    issues: list[str] = []
    if source.signal != target.signal:
        issues.append("signal type differs")
    if source.units != target.units:
        issues.append("units differ")
    if source.reference_frame != target.reference_frame:
        issues.append("reference_frame differs")
    source_labels = set(source.labels)
    target_labels = set(target.labels)
    mapped_sources = {rule.source_label for rule in rules}
    mapped_targets = {rule.target_label for rule in rules}
    if len(mapped_sources) != len(rules):
        issues.append("source labels are duplicated")
    if mapped_sources - source_labels:
        issues.append("mapping references unknown source labels")
    if mapped_targets - target_labels:
        issues.append("mapping references unknown target labels")
    if source_labels - mapped_sources:
        issues.append("source labels are unmapped")
    if target_labels - mapped_targets:
        issues.append("target labels are unmapped")
    if len(mapped_targets) != len(rules):
        issues.append("target labels are duplicated")
    return issues


def validate_representation_mapping(
    source: EmbodimentRef,
    source_representation: RepresentationSpec,
    target: EmbodimentRef,
    target_representation: RepresentationSpec,
    mapping: MappingSpec,
) -> list[str]:
    issues = validate_mapping(
        SignalSpec(
            "source_action",
            "joint_position",
            source_representation.action.units,
            source_representation.action.joints,
            source_representation.action.base_frame,
        ),
        SignalSpec(
            "target_action",
            "joint_position",
            target_representation.action.units,
            target_representation.action.joints,
            target_representation.action.base_frame,
        ),
        mapping.rules,
    )
    if mapping.source.embodiment_id != source.embodiment_id:
        issues.append("mapping source embodiment differs")
    if mapping.target.embodiment_id != target.embodiment_id:
        issues.append("mapping target embodiment differs")
    if mapping.source.representation_id != source_representation.representation_id:
        issues.append("mapping source representation differs")
    if mapping.target.representation_id != target_representation.representation_id:
        issues.append("mapping target representation differs")
    if (
        source_representation.action.ordering == target_representation.action.ordering
        and not mapping.rules
    ):
        issues.append("explicit mapping rules are required at the evaluation boundary")
    return issues
