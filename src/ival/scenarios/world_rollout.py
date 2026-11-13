"""Portable URDF Studio world-rollout campaign and evidence contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .world_scene_package import WorldScenePackageManifest

WORLD_ROLLOUT_CHECKER_PROFILE_SCHEMA_VERSION = "world_rollout_checker_profile.v1"
WORLD_ROLLOUT_CAMPAIGN_SCHEMA_VERSION = "world_rollout_campaign.v1"
WORLD_ROLLOUT_DEFAULT_RUNNER_KIND = "local-cli"
WORLD_ROLLOUT_MAX_ARTIFACT_REFS = 128
WORLD_ROLLOUT_MAX_MODULE_SPECS = 64
WORLD_ROLLOUT_MAX_TRACE_RECORDS = 100_000
WORLD_ROLLOUT_MAX_DECISION_RECORDS = 100_000
WORLD_ROLLOUT_MAX_NDJSON_BYTES = 25_000_000
WORLD_ROLLOUT_DECISIONS = frozenset({"allow", "warn", "reject", "stop", "escalate"})


@dataclass(frozen=True)
class WorldRolloutArtifactRef:
    kind: str
    uri: str
    digest_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldRolloutModuleSpec:
    module_id: str
    tier: str
    role: str
    trigger: str | None = None
    latency_budget_ms: float | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldRolloutCheckerProfile:
    profile_id: str
    target_id: str
    description: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    modules: tuple[WorldRolloutModuleSpec, ...] = ()
    artifacts: tuple[WorldRolloutArtifactRef, ...] = ()
    schema_version: str = WORLD_ROLLOUT_CHECKER_PROFILE_SCHEMA_VERSION


@dataclass(frozen=True)
class WorldRolloutPackageRef:
    package_id: str
    version: str
    digest_sha256: str | None = None


@dataclass(frozen=True)
class WorldRolloutRunnerSpec:
    kind: str = WORLD_ROLLOUT_DEFAULT_RUNNER_KIND
    tool: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldRolloutCampaignManifest:
    campaign_id: str
    world_package: WorldRolloutPackageRef
    checker_profile: WorldRolloutCheckerProfile
    rollout_params: dict[str, Any] = field(default_factory=dict)
    runner: WorldRolloutRunnerSpec = field(default_factory=WorldRolloutRunnerSpec)
    artifacts: tuple[WorldRolloutArtifactRef, ...] = ()
    schema_version: str = WORLD_ROLLOUT_CAMPAIGN_SCHEMA_VERSION


@dataclass(frozen=True)
class WorldRolloutTraceRecord:
    t_ms: int
    stream: str = "state"
    module_id: str | None = None
    tier: str | None = None
    state: dict[str, Any] = field(default_factory=dict)
    semantic_outputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldRolloutDecisionRecord:
    decision: str
    rule_id: str
    t_ms: int | None = None
    module_id: str | None = None
    tier: str | None = None
    subject_ref: str | None = None
    message: str | None = None
    confidence: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    semantic_outputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldRolloutImport:
    campaign: WorldRolloutCampaignManifest
    trace_records: tuple[WorldRolloutTraceRecord, ...]
    decisions: tuple[WorldRolloutDecisionRecord, ...]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "trace_record_count": len(self.trace_records),
            "decision_count": len(self.decisions),
            "reject_count": sum(item.decision == "reject" for item in self.decisions),
            "warn_count": sum(item.decision == "warn" for item in self.decisions),
            "stop_count": sum(item.decision == "stop" for item in self.decisions),
            "escalation_count": sum(item.decision == "escalate" for item in self.decisions),
        }


def build_world_rollout_campaign(
    world_package: WorldScenePackageManifest,
    checker_profile: WorldRolloutCheckerProfile,
    *,
    campaign_id: str | None = None,
    rollout_params: dict[str, Any] | None = None,
    runner_params: dict[str, Any] | None = None,
) -> WorldRolloutCampaignManifest:
    package_digest = _model_digest(world_package.to_dict())
    profile_digest = _model_digest(asdict(checker_profile))
    return WorldRolloutCampaignManifest(
        campaign_id=campaign_id or f"{world_package.package_id}-{world_package.version}",
        world_package=WorldRolloutPackageRef(world_package.package_id, world_package.version, package_digest),
        checker_profile=checker_profile,
        rollout_params=rollout_params or {},
        runner=WorldRolloutRunnerSpec(params=runner_params or {}),
        artifacts=(
            WorldRolloutArtifactRef("world_package_manifest", "world_package.json", package_digest),
            WorldRolloutArtifactRef("checker_profile", "checker_profile.json", profile_digest),
        ),
    )


def import_world_rollout_results(
    campaign: WorldRolloutCampaignManifest,
    *,
    trace_ndjson: str = "",
    decisions_ndjson: str = "",
) -> WorldRolloutImport:
    _verify_inline_digest(campaign, "trace_ndjson", trace_ndjson)
    _verify_inline_digest(campaign, "decisions_ndjson", decisions_ndjson)
    traces = tuple(_parse_ndjson(trace_ndjson, WorldRolloutTraceRecord, WORLD_ROLLOUT_MAX_TRACE_RECORDS, "trace_ndjson"))
    decisions = tuple(_parse_ndjson(decisions_ndjson, WorldRolloutDecisionRecord, WORLD_ROLLOUT_MAX_DECISION_RECORDS, "decisions_ndjson"))
    return WorldRolloutImport(campaign, traces, decisions)


def _parse_ndjson(raw: str, model: type[Any], max_records: int, label: str) -> list[Any]:
    if len(raw.encode("utf-8")) > WORLD_ROLLOUT_MAX_NDJSON_BYTES:
        raise ValueError(f"{label} exceeds the world rollout import limit")
    parsed: list[Any] = []
    for line_index, line in enumerate(raw.splitlines()):
        if not line.strip():
            continue
        if len(parsed) >= max_records:
            raise ValueError(f"{label} exceeds the record limit")
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("record must be an object")
            if model is WorldRolloutTraceRecord:
                value["t_ms"] = _nonnegative_int(value.get("t_ms"), "t_ms")
                value["stream"] = _required_text(value.get("stream", "state"), "stream")
                parsed.append(WorldRolloutTraceRecord(**_known(value, WorldRolloutTraceRecord)))
            else:
                decision = _required_text(value.get("decision"), "decision")
                if decision not in WORLD_ROLLOUT_DECISIONS:
                    raise ValueError("decision must be allow, warn, reject, stop, or escalate")
                value["rule_id"] = _required_text(value.get("rule_id"), "rule_id")
                if value.get("t_ms") is not None:
                    value["t_ms"] = _nonnegative_int(value["t_ms"], "t_ms")
                if value.get("confidence") is not None and not 0 <= float(value["confidence"]) <= 1:
                    raise ValueError("confidence must be between 0 and 1")
                parsed.append(WorldRolloutDecisionRecord(**_known(value, WorldRolloutDecisionRecord)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"{label} line {line_index + 1} is invalid: {exc}") from exc
    return parsed


def _verify_inline_digest(campaign: WorldRolloutCampaignManifest, kind: str, raw: str) -> None:
    artifact = next((item for item in campaign.artifacts if item.kind == kind), None)
    if artifact is not None and artifact.digest_sha256 is not None:
        actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if actual.lower() != artifact.digest_sha256.lower():
            raise ValueError(f"World rollout artifact digest mismatch: {artifact.uri}")


def _model_digest(payload: Any) -> str:
    raw = json.dumps(_jsonable(payload), indent=2, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _known(value: dict[str, Any], model: type[Any]) -> dict[str, Any]:
    names = set(model.__dataclass_fields__)
    return {key: item for key, item in value.items() if key in names}


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value

