from __future__ import annotations

from dataclasses import dataclass
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
    if source_labels - mapped_sources:
        issues.append("source labels are unmapped")
    if target_labels - mapped_targets:
        issues.append("target labels are unmapped")
    if len(mapped_targets) != len(rules):
        issues.append("target labels are duplicated")
    return issues
