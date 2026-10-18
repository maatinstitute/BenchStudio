"""Source-backed dataset/embodiment alignment registry.

The persistence and validation boundary follows ``urdf-ops``' dataset
alignment service. Fingerprinting is injected because the owning URDF runtime
may live in another process; this module never silently invents kinematic
identity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

ALIGNMENT_REGISTRY_FILE_VERSION = 1
KINEMATIC_FINGERPRINT_VERSION_V1 = "v1"
DEFAULT_SEMANTIC_REPRESENTATION_ID = "rep:joint_pos_abs:semantic:v1"
DEFAULT_INDEXED_REPRESENTATION_ID = "rep:joint_pos_abs:indexed:v1"
NAMING_STATUS_NAMED = "named"
NAMING_STATUS_UNNAMED = "unnamed"
UNKNOWN_EMBODIMENT_PREFIX = "unknown:"
UNKNOWN_UNFINGERPRINTED_EMBODIMENT_ID = "unknown:unfingerprinted"
EMBODIMENT_HASH_SUFFIX_LENGTH = 16


@dataclass(frozen=True)
class AlignmentEmbodiment:
    embodiment_id: str
    kinematic_fingerprint: str | None = None
    kinematic_fingerprint_version: str | None = None
    robot_type: str | None = None
    urdf_sha256: str | None = None
    srdf_sha256: str | None = None
    base_frame: str | None = None
    ee_frame: str | None = None


@dataclass(frozen=True)
class AlignmentEndpoint:
    embodiment_id: str
    representation_id: str


@dataclass(frozen=True)
class AlignmentJointRule:
    source_joint: str
    target_joint: str
    scale: float = 1.0
    offset: float = 0.0
    invert: bool = False
    unit: str = "rad"


@dataclass(frozen=True)
class AlignmentMapping:
    source: AlignmentEndpoint
    target: AlignmentEndpoint
    joint_rules: tuple[AlignmentJointRule, ...] = ()
    mapping_id: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    version: str = "v1"


@dataclass(frozen=True)
class EmbodimentResolveRequest:
    embodiment_id: str | None = None
    urdf_xml: str | None = None
    robot_type: str | None = None
    base_frame: str | None = None
    ee_frame: str | None = None


@dataclass(frozen=True)
class EmbodimentResolveResult:
    embodiment: AlignmentEmbodiment
    matched_existing: bool


@dataclass(frozen=True)
class DatasetAlignmentInput:
    dataset_id: str
    embodiment_id: str | None = None
    representation_id: str = DEFAULT_INDEXED_REPRESENTATION_ID
    naming_status: str = NAMING_STATUS_NAMED


@dataclass(frozen=True)
class DatasetAlignmentValidation:
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlignmentQuery:
    source_embodiment_id: str | None = None
    source_representation_id: str | None = None
    target_embodiment_id: str | None = None
    target_representation_id: str | None = None


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _mapping_payload(mapping: AlignmentMapping) -> dict[str, object]:
    return {
        "source": asdict(mapping.source),
        "target": asdict(mapping.target),
        "joint_rules": [asdict(rule) for rule in mapping.joint_rules],
        "version": mapping.version,
    }


class DatasetAlignmentRegistry:
    """Persistent embodiment and representation mapping registry."""

    def __init__(
        self,
        path: Path,
        *,
        fingerprint_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.path = Path(path)
        self.fingerprint_resolver = fingerprint_resolver

    def resolve_embodiment(self, request: EmbodimentResolveRequest) -> EmbodimentResolveResult:
        state = self._load()
        provided_id = _normalized(request.embodiment_id)
        if provided_id and provided_id in state["embodiments"]:
            return EmbodimentResolveResult(state["embodiments"][provided_id], True)
        robot_type = _normalized(request.robot_type)
        base_frame = _normalized(request.base_frame)
        ee_frame = _normalized(request.ee_frame)
        urdf_xml = _normalized(request.urdf_xml)
        fingerprint = None
        urdf_sha256 = None
        if urdf_xml:
            urdf_sha256 = hashlib.sha256(urdf_xml.encode("utf-8")).hexdigest()
            if self.fingerprint_resolver is not None:
                fingerprint = self.fingerprint_resolver(urdf_xml)
            if fingerprint:
                for existing in state["embodiments"].values():
                    if existing.kinematic_fingerprint == fingerprint:
                        return EmbodimentResolveResult(existing, True)
        embodiment_id = provided_id
        if not embodiment_id:
            if fingerprint:
                embodiment_id = f"{UNKNOWN_EMBODIMENT_PREFIX}{fingerprint}"
            else:
                seed = _canonical(
                    {"robot_type": robot_type, "base_frame": base_frame, "ee_frame": ee_frame}
                )
                suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[
                    :EMBODIMENT_HASH_SUFFIX_LENGTH
                ]
                embodiment_id = (
                    f"{UNKNOWN_EMBODIMENT_PREFIX}{suffix}"
                    if seed
                    else UNKNOWN_UNFINGERPRINTED_EMBODIMENT_ID
                )
        embodiment = AlignmentEmbodiment(
            embodiment_id=embodiment_id,
            kinematic_fingerprint=fingerprint,
            kinematic_fingerprint_version=KINEMATIC_FINGERPRINT_VERSION_V1 if fingerprint else None,
            robot_type=robot_type,
            urdf_sha256=urdf_sha256,
            base_frame=base_frame,
            ee_frame=ee_frame,
        )
        state["embodiments"][embodiment_id] = embodiment
        self._save(state)
        return EmbodimentResolveResult(embodiment, False)

    def list_embodiments(self) -> list[AlignmentEmbodiment]:
        return sorted(self._load()["embodiments"].values(), key=lambda item: item.embodiment_id)

    def upsert_mapping(self, mapping: AlignmentMapping) -> AlignmentMapping:
        state = self._load()
        mapping_id = mapping.mapping_id or self._mapping_id(mapping)
        saved = AlignmentMapping(
            source=mapping.source,
            target=mapping.target,
            joint_rules=mapping.joint_rules,
            mapping_id=mapping_id,
            created_by=mapping.created_by,
            created_at=mapping.created_at or datetime.now(timezone.utc).isoformat(),
            version=mapping.version,
        )
        state["mappings"][mapping_id] = saved
        self._save(state)
        return saved

    def list_mappings(self, query: AlignmentQuery | None = None) -> list[AlignmentMapping]:
        mappings = list(self._load()["mappings"].values())
        if query:
            mappings = [
                mapping
                for mapping in mappings
                if not query.source_embodiment_id
                or mapping.source.embodiment_id == query.source_embodiment_id
                if not query.source_representation_id
                or mapping.source.representation_id == query.source_representation_id
                if not query.target_embodiment_id
                or mapping.target.embodiment_id == query.target_embodiment_id
                if not query.target_representation_id
                or mapping.target.representation_id == query.target_representation_id
            ]
        return sorted(mappings, key=lambda item: item.mapping_id or "")

    def validate_datasets(
        self,
        datasets: Iterable[DatasetAlignmentInput],
        *,
        required_representation_id: str | None = None,
    ) -> DatasetAlignmentValidation:
        values = list(datasets)
        errors: list[str] = []
        if not values:
            errors.append("At least one dataset alignment descriptor is required.")
            return DatasetAlignmentValidation(False, tuple(errors))
        mappings = self.list_mappings()
        representation_ids = {item.representation_id for item in values}
        if len(representation_ids) > 1 and not required_representation_id:
            errors.append(
                "Datasets have mixed representation_id values. Provide "
                "required_representation_id or explicit mappings."
            )
        for dataset in values:
            if not dataset.embodiment_id:
                errors.append(f"Dataset {dataset.dataset_id} is missing embodiment_id.")
            if dataset.naming_status == NAMING_STATUS_UNNAMED:
                errors.append(
                    f"Dataset {dataset.dataset_id} has unnamed joints; semantic "
                    "alignment is unsafe without mapping."
                )
            if (
                required_representation_id
                and dataset.representation_id != required_representation_id
            ):
                has_mapping = any(
                    mapping.source.representation_id == dataset.representation_id
                    and mapping.target.representation_id == required_representation_id
                    and (
                        not dataset.embodiment_id
                        or mapping.source.embodiment_id == dataset.embodiment_id
                    )
                    for mapping in mappings
                )
                if not has_mapping:
                    errors.append(
                        f"Dataset {dataset.dataset_id} uses {dataset.representation_id} "
                        "and has no MappingSpec to required representation "
                        f"{required_representation_id}."
                    )
        return DatasetAlignmentValidation(not errors, tuple(errors))

    def _mapping_id(self, mapping: AlignmentMapping) -> str:
        return (
            "map:"
            + hashlib.sha256(_canonical(_mapping_payload(mapping)).encode("utf-8")).hexdigest()[
                :EMBODIMENT_HASH_SUFFIX_LENGTH
            ]
        )

    def _load(self) -> dict[str, dict[str, object]]:
        if not self.path.is_file() or not self.path.read_text(encoding="utf-8").strip():
            return {"embodiments": {}, "mappings": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"embodiments": {}, "mappings": {}}
        embodiments = {
            key: AlignmentEmbodiment(**value)
            for key, value in payload.get("embodiments", {}).items()
            if isinstance(value, dict)
        }
        mappings: dict[str, AlignmentMapping] = {}
        for key, value in payload.get("mappings", {}).items():
            if not isinstance(value, dict):
                continue
            try:
                mappings[key] = AlignmentMapping(
                    source=AlignmentEndpoint(**value["source"]),
                    target=AlignmentEndpoint(**value["target"]),
                    joint_rules=tuple(
                        AlignmentJointRule(**rule) for rule in value.get("joint_rules", [])
                    ),
                    mapping_id=value.get("mapping_id"),
                    created_by=value.get("created_by"),
                    created_at=value.get("created_at"),
                    version=value.get("version", "v1"),
                )
            except (KeyError, TypeError, ValueError):
                continue
        return {"embodiments": embodiments, "mappings": mappings}

    def _save(self, state: dict[str, dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": ALIGNMENT_REGISTRY_FILE_VERSION,
            "embodiments": {key: asdict(value) for key, value in state["embodiments"].items()},
            "mappings": {key: asdict(value) for key, value in state["mappings"].items()},
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
