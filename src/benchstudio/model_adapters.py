from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import ModelCapabilityProfile, Policy


@dataclass(frozen=True)
class ModelDependency:
    name: str
    import_name: str
    required: bool = True
    scope: str = "runtime"


@dataclass(frozen=True)
class ModelAdapterDescriptor:
    adapter_id: str
    label: str
    factory: Callable[..., Policy]
    capabilities: ModelCapabilityProfile
    dependencies: tuple[ModelDependency, ...] = field(default_factory=tuple)


class ModelAdapterRegistry:
    """Dependency-aware registry for independently developed policy adapters."""

    def __init__(self) -> None:
        self._descriptors: dict[str, ModelAdapterDescriptor] = {}
        self._discovery_diagnostics: list[dict[str, str]] = []

    def register(self, descriptor: ModelAdapterDescriptor) -> None:
        if descriptor.adapter_id in self._descriptors:
            raise ValueError(f"model adapter already registered: {descriptor.adapter_id}")
        issues = descriptor.capabilities.validate()
        if issues:
            raise ValueError(
                f"invalid capabilities for model adapter {descriptor.adapter_id}: "
                + "; ".join(issues)
            )
        self._descriptors[descriptor.adapter_id] = descriptor

    def get(self, adapter_id: str) -> ModelAdapterDescriptor:
        try:
            return self._descriptors[adapter_id]
        except KeyError as exc:
            raise KeyError(f"unknown model adapter: {adapter_id}") from exc

    def list(self) -> list[ModelAdapterDescriptor]:
        return [self._descriptors[key] for key in sorted(self._descriptors)]

    def readiness(self, adapter_id: str) -> dict[str, Any]:
        descriptor = self.get(adapter_id)
        dependencies = []
        for dependency in descriptor.dependencies:
            available = _module_available(dependency.import_name)
            try:
                version = metadata.version(dependency.name)
            except metadata.PackageNotFoundError:
                version = None
            dependencies.append(
                {
                    "name": dependency.name,
                    "import_name": dependency.import_name,
                    "available": available,
                    "version": version,
                    "required": dependency.required,
                    "scope": dependency.scope,
                }
            )
        missing_required = [
            item["name"] for item in dependencies if item["required"] and not item["available"]
        ]
        return {
            "adapter_id": descriptor.adapter_id,
            "label": descriptor.label,
            "ready": not missing_required,
            "missing_required": missing_required,
            "capabilities": descriptor.capabilities,
            "dependencies": dependencies,
        }

    def create(self, adapter_id: str, **kwargs: Any) -> Policy:
        descriptor = self.get(adapter_id)
        readiness = self.readiness(adapter_id)
        if not readiness["ready"]:
            raise RuntimeError(
                f"model adapter {adapter_id} is not ready; missing: "
                + ", ".join(readiness["missing_required"])
            )
        policy = descriptor.factory(**kwargs)
        try:
            setattr(policy, "__benchstudio_capabilities__", descriptor.capabilities)
            setattr(policy, "__benchstudio_adapter_id__", descriptor.adapter_id)
        except (AttributeError, TypeError):
            # Immutable third-party policy objects can still execute; their
            # adapter descriptor remains available from the registry audit.
            pass
        return policy

    def validate_plan(self, plan: Any) -> tuple[str, ...]:
        """Validate the model adapter frozen in a campaign plan."""
        protocol = getattr(plan, "protocol", None) or {}
        if not isinstance(protocol, Mapping):
            return ("protocol must be a mapping",)
        model = protocol.get("M", {})
        if not isinstance(model, Mapping) or not model.get("adapter"):
            return ()
        adapter_id = model["adapter"]
        try:
            readiness = self.readiness(adapter_id)
        except KeyError:
            return (f"unknown model adapter {adapter_id}",)
        if not readiness["ready"]:
            return (
                f"model adapter {adapter_id} missing " + ", ".join(readiness["missing_required"]),
            )
        declared = model.get("capabilities")
        if declared is not None:
            try:
                declared_profile = _profile_from_mapping(declared)
            except (TypeError, ValueError) as exc:
                return (f"model adapter {adapter_id} has invalid frozen capabilities: {exc}",)
            actual = self.get(adapter_id).capabilities.to_dict()
            declared_values = declared_profile.to_dict()
            mismatches = tuple(
                name for name in sorted(declared) if declared_values[name] != actual.get(name)
            )
            if mismatches:
                return (
                    f"model adapter {adapter_id} capability mismatch: " + ", ".join(mismatches),
                )
        evaluation = protocol.get("P", {}).get("evaluation", {})
        strategy = evaluation.get("execution_strategy", "sync")
        capability_name = {
            "async": "supports_async",
            "streaming": "supports_streaming",
            "cached": "supports_cached_predictions",
        }.get(strategy)
        if capability_name and not getattr(self.get(adapter_id).capabilities, capability_name):
            return (f"model adapter {adapter_id} does not support {strategy} execution",)
        return ()

    def discover(self, group: str = "benchstudio.models") -> tuple[dict[str, str], ...]:
        entries = metadata.entry_points()
        selected = (
            entries.select(group=group) if hasattr(entries, "select") else entries.get(group, ())
        )
        diagnostics: list[dict[str, str]] = []
        for entry in selected:
            try:
                loaded = entry.load()
                value = loaded() if callable(loaded) else loaded
                descriptors = (
                    (value,) if isinstance(value, ModelAdapterDescriptor) else tuple(value)
                )
                if not descriptors or not all(
                    isinstance(item, ModelAdapterDescriptor) for item in descriptors
                ):
                    raise TypeError(
                        "entry point must return ModelAdapterDescriptor or an iterable of them"
                    )
                for descriptor in descriptors:
                    self.register(descriptor)
                diagnostics.append({"entry_point": entry.name, "status": "loaded"})
            except Exception as exc:
                diagnostics.append(
                    {
                        "entry_point": entry.name,
                        "status": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        self._discovery_diagnostics.extend(diagnostics)
        return tuple(diagnostics)

    @property
    def discovery_diagnostics(self) -> tuple[dict[str, str], ...]:
        return tuple(self._discovery_diagnostics)


def _module_available(import_name: str) -> bool:
    try:
        importlib.import_module(import_name)
    except ModuleNotFoundError as exc:
        if exc.name == import_name or import_name.startswith(f"{exc.name}."):
            return False
        raise
    return True


def _profile_from_mapping(value: Any) -> ModelCapabilityProfile:
    if not isinstance(value, Mapping):
        raise TypeError("capabilities must be a mapping")
    payload = dict(value)
    for name in ("input_modalities", "supported_metrics", "runtime_controls", "timing_signals"):
        if name in payload:
            raw = payload[name]
            if isinstance(raw, (str, bytes)):
                raise TypeError(f"{name} must be a sequence of strings")
            payload[name] = tuple(raw)
    profile = ModelCapabilityProfile(**payload)
    issues = profile.validate()
    if issues:
        raise ValueError("; ".join(issues))
    return profile


def default_model_registry(*, discover_external: bool = True) -> ModelAdapterRegistry:
    from .external_policy import (
        ExternalCommandPolicy,
        PersistentExternalCommandPolicy,
        external_command_capabilities,
        external_vla_capabilities,
        persistent_external_command_capabilities,
    )
    from .integrations.policy_trace import TracePolicy
    from .mock import MockPolicy

    registry = ModelAdapterRegistry()
    registry.register(
        ModelAdapterDescriptor(
            adapter_id="mock",
            label="Deterministic mock policy",
            factory=MockPolicy,
            capabilities=ModelCapabilityProfile(
                model_id="mock_policy",
                family="custom",
                input_modalities=("state",),
                output_representation="action_chunk",
                supports_closed_loop=True,
                supports_action_chunks=True,
                supported_metrics=("success",),
                supports_cached_predictions=True,
            ),
        )
    )
    registry.register(
        ModelAdapterDescriptor(
            adapter_id="trace",
            label="Digest-bound frozen policy trace",
            factory=lambda path, policy_id="trace_policy", trace_sha256=None: (
                TracePolicy.from_jsonl(
                    Path(path), policy_id=policy_id, expected_sha256=trace_sha256
                )
            ),
            capabilities=ModelCapabilityProfile(
                model_id="trace_policy",
                family="custom",
                input_modalities=("state", "image", "proprioception"),
                output_representation="action_chunk",
                supports_closed_loop=True,
                supports_action_chunks=True,
                supported_metrics=("success", "parity"),
                runtime_controls=("path", "digest_bound_observations"),
            ),
        )
    )
    registry.register(
        ModelAdapterDescriptor(
            adapter_id="persistent_external_command",
            label="Persistent external JSON policy process",
            factory=PersistentExternalCommandPolicy,
            capabilities=persistent_external_command_capabilities(),
        )
    )
    registry.register(
        ModelAdapterDescriptor(
            adapter_id="external_command",
            label="External JSON policy process",
            factory=ExternalCommandPolicy,
            capabilities=external_command_capabilities(),
        )
    )
    for adapter_id, label in (
        ("smolvla", "SmolVLA external JSON-line protocol bridge"),
        ("opendm", "OpenDM/DM0.5 external JSON-line protocol bridge"),
    ):
        registry.register(
            ModelAdapterDescriptor(
                adapter_id=adapter_id,
                label=label,
                factory=PersistentExternalCommandPolicy,
                capabilities=external_vla_capabilities(adapter_id),
            )
        )
    if discover_external:
        registry.discover()
    return registry
