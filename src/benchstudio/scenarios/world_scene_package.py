"""Dependency-free port of the URDF Studio world-scene package boundary."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal

WORLD_SCENE_PACKAGE_SCHEMA_VERSION_V1 = "1.0.0"
MAX_SCENARIO_DURATION_MS = 600_000
MAX_RUNTIME_TARGETS = 16
MAX_INTERFACE_MODALITIES = 32
MAX_ARTIFACT_REFS = 128
MAX_CAMERAS_PER_WORLD = 64
MAX_OBJECTS_PER_WORLD = 256
MAX_JOINTS_PER_WORLD = 512
MAX_WORLD_SNAPSHOT_URDF_CHARS = 500_000
MAX_WORLD_SCENE_PACKAGE_MANIFEST_BYTES = 1_000_000
REGISTRY_FILE_VERSION = 1

TrustLevel = Literal["metadata_only", "signed_metadata", "metadata_complete"]


@dataclass(frozen=True)
class WorldRuntimeTarget:
    name: str
    mode: Literal["native", "python", "container"]
    min_version: str | None = None


@dataclass(frozen=True)
class WorldInterfaceSpec:
    observation_modalities: tuple[str, ...]
    action_semantics: str
    timestep_ms: int
    frame_convention: str


@dataclass(frozen=True)
class WorldArtifactRef:
    kind: str
    digest_sha256: str
    uri: str


@dataclass(frozen=True)
class WorldSecuritySpec:
    signature_ref: str | None = None
    attestation_refs: tuple[str, ...] = ()
    sbom_ref: str | None = None


@dataclass(frozen=True)
class WorldSnapshot:
    urdf_xml: str
    joint_positions: dict[str, float] = field(default_factory=dict)
    cameras: tuple[dict[str, Any], ...] = ()
    objects: tuple[dict[str, Any], ...] = ()
    scenario_time_ms: int = 0
    scenario_duration_ms: int = 0


@dataclass(frozen=True)
class WorldScenePackageManifest:
    schema_version: str
    package_id: str
    version: str
    title: str
    created_at: str
    interface: WorldInterfaceSpec
    world_snapshot: WorldSnapshot
    description: str | None = None
    runtime_targets: tuple[WorldRuntimeTarget, ...] = ()
    artifacts: tuple[WorldArtifactRef, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    security: WorldSecuritySpec = field(default_factory=WorldSecuritySpec)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorldScenePackageManifest":
        if not isinstance(payload, dict):
            raise ValueError("world scene package manifest must be an object")
        interface = payload.get("interface")
        snapshot = payload.get("world_snapshot")
        if not isinstance(interface, dict) or not isinstance(snapshot, dict):
            raise ValueError("manifest requires interface and world_snapshot objects")
        manifest = cls(
            schema_version=str(payload.get("schema_version", WORLD_SCENE_PACKAGE_SCHEMA_VERSION_V1)),
            package_id=_required_text(payload, "package_id"),
            version=_required_text(payload, "version"),
            title=_required_text(payload, "title"),
            description=payload.get("description"),
            created_at=_required_text(payload, "created_at"),
            runtime_targets=tuple(WorldRuntimeTarget(**item) for item in payload.get("runtime_targets", [])),
            interface=WorldInterfaceSpec(
                tuple(interface.get("observation_modalities", [])),
                _required_text(interface, "action_semantics"),
                int(interface["timestep_ms"]),
                _required_text(interface, "frame_convention"),
            ),
            artifacts=tuple(WorldArtifactRef(**item) for item in payload.get("artifacts", [])),
            world_snapshot=WorldSnapshot(
                urdf_xml=_required_text(snapshot, "urdf_xml"),
                joint_positions={str(k): float(v) for k, v in snapshot.get("joint_positions", {}).items()},
                cameras=tuple(snapshot.get("cameras", [])),
                objects=tuple(snapshot.get("objects", [])),
                scenario_time_ms=int(snapshot.get("scenario_time_ms", 0)),
                scenario_duration_ms=int(snapshot.get("scenario_duration_ms", 0)),
            ),
            provenance=dict(payload.get("provenance", {})),
            security=WorldSecuritySpec(
                signature_ref=payload.get("security", {}).get("signature_ref"),
                attestation_refs=tuple(payload.get("security", {}).get("attestation_refs", [])),
                sbom_ref=payload.get("security", {}).get("sbom_ref"),
            ),
        )
        issues = validate_world_scene_package(manifest)
        if issues:
            raise ValueError("invalid world scene package: " + "; ".join(issues))
        return manifest


@dataclass(frozen=True)
class WorldScenePackageVersionRecord:
    package_id: str
    version: str
    digest_sha256: str
    published_at: str
    manifest: WorldScenePackageManifest

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(frozen=True)
class WorldScenePackageValidationResponse:
    valid: bool
    digest_sha256: str
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorldRegistryCapabilities:
    source: str
    available: bool
    can_list: bool
    can_get_version: bool
    can_publish: bool


@dataclass(frozen=True)
class WorldScenePackageListEntry:
    package_id: str
    latest_version: str
    latest_digest_sha256: str
    updated_at: str
    title: str
    description: str | None
    owner: str | None
    tags: tuple[str, ...]
    preview_image_url: str | None
    source_registry: str | None
    trust_level: TrustLevel
    runtime_targets: tuple[str, ...]


def world_scene_package_digest(manifest: WorldScenePackageManifest) -> str:
    canonical = json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_world_scene_package(manifest: WorldScenePackageManifest) -> list[str]:
    errors: list[str] = []
    if manifest.schema_version != WORLD_SCENE_PACKAGE_SCHEMA_VERSION_V1:
        errors.append(f"unsupported schema_version: {manifest.schema_version}")
    if len(manifest.runtime_targets) > MAX_RUNTIME_TARGETS:
        errors.append("runtime_targets exceeds maximum")
    if len(manifest.interface.observation_modalities) > MAX_INTERFACE_MODALITIES:
        errors.append("observation_modalities exceeds maximum")
    if len(manifest.artifacts) > MAX_ARTIFACT_REFS:
        errors.append("artifacts exceeds maximum")
    snapshot = manifest.world_snapshot
    if not snapshot.urdf_xml or len(snapshot.urdf_xml) > MAX_WORLD_SNAPSHOT_URDF_CHARS:
        errors.append("urdf_xml is empty or exceeds maximum length")
    if len(snapshot.joint_positions) > MAX_JOINTS_PER_WORLD:
        errors.append("joint_positions exceeds maximum")
    if len(snapshot.cameras) > MAX_CAMERAS_PER_WORLD or len(snapshot.objects) > MAX_OBJECTS_PER_WORLD:
        errors.append("world snapshot collection exceeds maximum")
    if snapshot.scenario_duration_ms < 0 or snapshot.scenario_duration_ms > MAX_SCENARIO_DURATION_MS:
        errors.append("scenario_duration_ms is outside allowed bounds")
    if snapshot.scenario_time_ms < 0 or snapshot.scenario_time_ms > snapshot.scenario_duration_ms:
        errors.append("scenario_time_ms must be between zero and scenario_duration_ms")
    if snapshot.scenario_duration_ms == 0 and snapshot.scenario_time_ms != 0:
        errors.append("scenario_time_ms must be 0 when scenario_duration_ms is 0")
    if manifest.interface.timestep_ms < 1:
        errors.append("timestep_ms must be positive")
    if any(not math.isfinite(value) for value in snapshot.joint_positions.values()):
        errors.append("joint_positions must be finite")
    return errors


class WorldScenePackageRegistry:
    """Small file-backed registry matching the URDF Studio registry boundary."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = Lock()

    def validate(self, manifest: WorldScenePackageManifest) -> WorldScenePackageValidationResponse:
        errors = validate_world_scene_package(manifest)
        canonical_size = len(json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if canonical_size > MAX_WORLD_SCENE_PACKAGE_MANIFEST_BYTES:
            errors.append(
                "World scene package manifest exceeds the allowed serialized size: "
                f"{canonical_size} > {MAX_WORLD_SCENE_PACKAGE_MANIFEST_BYTES} bytes."
            )
        warnings: list[str] = []
        if not manifest.runtime_targets:
            warnings.append("No runtime_targets declared. Cross-runtime compatibility cannot be inferred.")
        if not manifest.artifacts:
            warnings.append("No external artifacts declared. Package is embedded-only.")
        if not manifest.security.signature_ref:
            warnings.append("No signature_ref present. Package remains metadata-only.")
        return WorldScenePackageValidationResponse(
            not errors, world_scene_package_digest(manifest), tuple(warnings), tuple(errors)
        )

    def get_capabilities(self) -> WorldRegistryCapabilities:
        return WorldRegistryCapabilities(
            source="urdf-studio-world-registry", available=True,
            can_list=True, can_get_version=True, can_publish=True,
        )

    def publish(self, manifest: WorldScenePackageManifest) -> WorldScenePackageVersionRecord:
        validation = self.validate(manifest)
        if not validation.valid:
            raise ValueError("invalid world scene package: " + "; ".join(validation.errors))
        with self._lock:
            state = self._load()
            versions = state.setdefault(manifest.package_id, {})
            if manifest.version in versions:
                raise FileExistsError(f"Package {manifest.package_id} version {manifest.version} already exists.")
            record = WorldScenePackageVersionRecord(
                manifest.package_id, manifest.version, world_scene_package_digest(manifest),
                datetime.now(timezone.utc).isoformat(), manifest,
            )
            versions[manifest.version] = record.to_dict()
            self._save(state)
            return record

    def get_version(self, package_id: str, version: str) -> WorldScenePackageVersionRecord:
        with self._lock:
            payload = self._load().get(package_id, {}).get(version)
        if payload is None:
            raise KeyError(f"Version {version} was not found for package {package_id}.")
        return WorldScenePackageVersionRecord(
            payload["package_id"], payload["version"], payload["digest_sha256"],
            payload["published_at"], WorldScenePackageManifest.from_dict(payload["manifest"]),
        )

    def list_packages(
        self, *, query: str | None = None, owner: str | None = None,
        tags: tuple[str, ...] | list[str] | None = None,
        limit: int = 200, offset: int = 0,
    ) -> list[WorldScenePackageListEntry]:
        with self._lock:
            packages = self._load()
        entries: list[WorldScenePackageListEntry] = []
        for package_id, versions in packages.items():
            records = [self._record_from_payload(item) for item in versions.values()]
            if not records:
                continue
            latest = max(records, key=lambda record: record.published_at)
            manifest = latest.manifest
            provenance = manifest.provenance
            entry = WorldScenePackageListEntry(
                package_id=package_id,
                latest_version=latest.version,
                latest_digest_sha256=latest.digest_sha256,
                updated_at=latest.published_at,
                title=manifest.title,
                description=manifest.description,
                owner=_optional_text(provenance.get("owner")),
                tags=tuple(sorted({_optional_text(value).lower() for value in provenance.get("tags", []) if _optional_text(value)})),
                preview_image_url=_optional_text(provenance.get("preview_image_url")),
                source_registry=_optional_text(provenance.get("source_registry")),
                trust_level=_resolve_trust_level(manifest),
                runtime_targets=tuple(f"{target.name}:{target.mode}" for target in manifest.runtime_targets),
            )
            if _matches_package_entry(entry, query=query, owner=owner, tags=tags):
                entries.append(entry)
        entries.sort(key=lambda item: item.updated_at, reverse=True)
        start = max(offset, 0)
        return entries[start:start + max(limit, 0)]

    def _record_from_payload(self, payload: dict[str, Any]) -> WorldScenePackageVersionRecord:
        return WorldScenePackageVersionRecord(
            payload["package_id"], payload["version"], payload["digest_sha256"],
            payload["published_at"], WorldScenePackageManifest.from_dict(payload["manifest"]),
        )

    def _load(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload.get("packages", {}) if isinstance(payload, dict) and isinstance(payload.get("packages", {}), dict) else {}

    def _save(self, packages: dict[str, dict[str, dict[str, Any]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"registry_file_version": REGISTRY_FILE_VERSION, "packages": packages}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _resolve_trust_level(manifest: WorldScenePackageManifest) -> TrustLevel:
    security = manifest.security
    if security.signature_ref and security.attestation_refs and security.sbom_ref:
        return "metadata_complete"
    if security.signature_ref:
        return "signed_metadata"
    return "metadata_only"


def _matches_package_entry(
    entry: WorldScenePackageListEntry, *, query: str | None, owner: str | None,
    tags: tuple[str, ...] | list[str] | None,
) -> bool:
    normalized_query = (query or "").strip().lower()
    if normalized_query:
        haystacks = (entry.package_id, entry.latest_version, entry.title,
                     entry.description or "", entry.owner or "",
                     " ".join(entry.tags), " ".join(entry.runtime_targets))
        if not any(normalized_query in value.lower() for value in haystacks):
            return False
    normalized_owner = (owner or "").strip().lower()
    if normalized_owner and (entry.owner or "").lower() != normalized_owner:
        return False
    requested = {str(value).strip().lower() for value in (tags or ()) if str(value).strip()}
    return requested.issubset(set(entry.tags))


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
