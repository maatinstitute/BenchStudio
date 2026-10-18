from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any, Callable, Mapping

from .contracts import Simulator


@dataclass(frozen=True)
class Dependency:
    name: str
    import_name: str
    required: bool = True
    scope: str = "runtime"


@dataclass(frozen=True)
class BackendCapabilities:
    """Declared authority and fidelity properties of an execution backend."""

    owns_physics: bool = False
    owns_official_scoring: bool = False
    owns_hardware_safety: bool = False
    closed_loop: bool = False
    evidence_authority: str = "benchstudio"


@dataclass(frozen=True)
class AdapterDescriptor:
    simulator_id: str
    label: str
    factory: Callable[..., Simulator]
    dependencies: tuple[Dependency, ...] = field(default_factory=tuple)
    capabilities: BackendCapabilities = field(default_factory=BackendCapabilities)


class AdapterRegistry:
    """Explicit simulator registry with dependency-aware readiness reporting."""

    def __init__(self) -> None:
        self._descriptors: dict[str, AdapterDescriptor] = {}
        self._discovery_diagnostics: list[dict[str, str]] = []

    def register(self, descriptor: AdapterDescriptor) -> None:
        if descriptor.simulator_id in self._descriptors:
            raise ValueError(f"simulator adapter already registered: {descriptor.simulator_id}")
        self._descriptors[descriptor.simulator_id] = descriptor

    def get(self, simulator_id: str) -> AdapterDescriptor:
        try:
            return self._descriptors[simulator_id]
        except KeyError as exc:
            raise KeyError(f"unknown simulator adapter: {simulator_id}") from exc

    def list(self) -> list[AdapterDescriptor]:
        return [self._descriptors[key] for key in sorted(self._descriptors)]

    def readiness(self, simulator_id: str) -> dict[str, Any]:
        descriptor = self.get(simulator_id)
        dependencies = []
        for dependency in descriptor.dependencies:
            available = module_available(dependency.import_name)
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
            "simulator_id": descriptor.simulator_id,
            "label": descriptor.label,
            "ready": not missing_required,
            "missing_required": missing_required,
            "dependencies": dependencies,
            "capabilities": {
                "owns_physics": descriptor.capabilities.owns_physics,
                "owns_official_scoring": descriptor.capabilities.owns_official_scoring,
                "owns_hardware_safety": descriptor.capabilities.owns_hardware_safety,
                "closed_loop": descriptor.capabilities.closed_loop,
                "evidence_authority": descriptor.capabilities.evidence_authority,
            },
        }

    def create(
        self,
        simulator_id: str,
        *,
        required_capabilities: Mapping[str, bool] | None = None,
        **kwargs: Any,
    ) -> Simulator:
        descriptor = self.get(simulator_id)
        readiness = self.readiness(simulator_id)
        if not readiness["ready"]:
            missing = ", ".join(readiness["missing_required"])
            raise RuntimeError(f"simulator {simulator_id} is not ready; missing: {missing}")
        issues = self.capability_issues(simulator_id, required_capabilities or {})
        if issues:
            raise RuntimeError(
                f"simulator {simulator_id} does not satisfy required capabilities: "
                + ", ".join(issues)
            )
        simulator = descriptor.factory(**kwargs)
        try:
            setattr(simulator, "__benchstudio_dependencies__", tuple(readiness["dependencies"]))
            setattr(simulator, "__benchstudio_adapter_id__", descriptor.simulator_id)
        except (AttributeError, TypeError):
            # Immutable third-party simulator objects can still execute; the
            # descriptor remains available from the registry audit.
            pass
        return simulator

    def capability_issues(self, simulator_id: str, required: Mapping[str, bool]) -> tuple[str, ...]:
        """Return unmet boolean capability requirements in stable order."""
        capabilities = self.get(simulator_id).capabilities
        issues: list[str] = []
        for name in sorted(required):
            expected = required[name]
            if not isinstance(expected, bool):
                raise TypeError(f"capability requirement {name!r} must be boolean")
            actual = getattr(capabilities, name, None)
            if actual is None:
                raise ValueError(f"unknown backend capability: {name}")
            if expected and not actual:
                issues.append(name)
        return tuple(issues)

    def validate_plan(self, plan: Any) -> tuple[str, ...]:
        """Validate backend declarations frozen in a campaign plan."""
        protocol = getattr(plan, "protocol", None) or {}
        issues: list[str] = []
        if not isinstance(protocol, Mapping):
            return ("protocol must be a mapping",)
        system = protocol.get("S", {})
        if not isinstance(system, Mapping):
            return ("protocol.S must be a mapping",)
        environments = system.get("environments", [])
        if not isinstance(environments, list):
            return ("protocol.S.environments must be a list",)
        seen_ids: set[str] = set()
        for environment in environments:
            if not isinstance(environment, Mapping):
                issues.append("environment declaration must be a mapping")
                continue
            # Generic environment declarations remain valid for callers that
            # provide an explicit simulator_factory. Only adapter-backed
            # declarations are owned by this registry and need these checks.
            if "adapter" not in environment:
                continue
            environment_id = environment.get("id")
            if not isinstance(environment_id, str) or not environment_id:
                issues.append("environment declaration requires a non-empty string id")
                environment_id = "<unknown>"
            elif environment_id in seen_ids:
                issues.append(f"duplicate environment id {environment_id}")
            else:
                seen_ids.add(environment_id)
            simulator_id = environment.get("adapter")
            if not isinstance(simulator_id, str) or not simulator_id:
                issues.append(f"{environment_id}: adapter must be a non-empty string")
                continue
            adapter_config = environment.get("adapter_config", {})
            if not isinstance(adapter_config, Mapping):
                issues.append(f"{environment_id}: adapter_config must be a mapping")
            required = environment.get("required_capabilities", {})
            if not isinstance(required, Mapping):
                issues.append(f"{environment_id}: required_capabilities must be a mapping")
                required = {}
            try:
                readiness = self.readiness(simulator_id)
            except KeyError:
                issues.append(f"{environment_id}: unknown adapter {simulator_id}")
                continue
            if not readiness["ready"]:
                issues.append(
                    f"{environment_id}: adapter {simulator_id} missing "
                    + ", ".join(readiness["missing_required"])
                )
            try:
                capability_issues = self.capability_issues(simulator_id, required)
            except (TypeError, ValueError) as exc:
                issues.append(f"{environment_id}: {exc}")
            else:
                issues.extend(
                    f"{environment_id}: adapter {simulator_id} lacks {name}"
                    for name in capability_issues
                )
        return tuple(issues)

    def discover(self, group: str = "benchstudio.simulators") -> tuple[dict[str, str], ...]:
        """Load optional simulator adapters exposed through package entry points."""
        entries = metadata.entry_points()
        selected = (
            entries.select(group=group) if hasattr(entries, "select") else entries.get(group, ())
        )
        diagnostics: list[dict[str, str]] = []
        for entry in selected:
            try:
                loaded = entry.load()
                value = (
                    loaded()
                    if callable(loaded) and not isinstance(loaded, AdapterDescriptor)
                    else loaded
                )
                descriptors = (value,) if isinstance(value, AdapterDescriptor) else tuple(value)
                if not descriptors or not all(
                    isinstance(item, AdapterDescriptor) for item in descriptors
                ):
                    raise TypeError(
                        "entry point must return AdapterDescriptor or an iterable of them"
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


def module_available(import_name: str) -> bool:
    try:
        importlib.import_module(import_name)
    except ModuleNotFoundError as exc:
        if exc.name == import_name or import_name.startswith(f"{exc.name}."):
            return False
        raise
    return True


def default_registry(*, discover_external: bool = True) -> AdapterRegistry:
    from .external_simulator import ExternalCommandSimulator
    from .integrations.genesis import GenesisSimulator
    from .integrations.gymnasium import GymnasiumSimulator
    from .integrations.isaaclab import IsaacLabSimulator
    from .integrations.mujoco import MujocoSimulator
    from .mock import MockSimulator
    from .replay import ReplaySimulator

    registry = AdapterRegistry()
    registry.register(
        AdapterDescriptor(
            simulator_id="mock",
            label="Deterministic mock simulator",
            factory=MockSimulator,
        )
    )
    registry.register(
        AdapterDescriptor(
            simulator_id="trace_replay",
            label="URDF Studio-style trace replay facade",
            factory=ReplaySimulator,
        )
    )
    registry.register(
        AdapterDescriptor(
            simulator_id="mujoco",
            label="Optional MuJoCo physics simulator",
            factory=MujocoSimulator,
            dependencies=(Dependency("mujoco", "mujoco"),),
            capabilities=BackendCapabilities(
                owns_physics=True,
                closed_loop=True,
                evidence_authority="mujoco",
            ),
        )
    )
    registry.register(
        AdapterDescriptor(
            simulator_id="gymnasium",
            label="Optional Gymnasium environment adapter",
            factory=GymnasiumSimulator,
            dependencies=(Dependency("gymnasium", "gymnasium"),),
            capabilities=BackendCapabilities(
                closed_loop=True,
                evidence_authority="gymnasium",
            ),
        )
    )
    registry.register(
        AdapterDescriptor(
            simulator_id="genesis",
            label="Optional Genesis World scene adapter",
            factory=GenesisSimulator,
            dependencies=(Dependency("genesis-world", "genesis"),),
            capabilities=BackendCapabilities(
                owns_physics=True,
                closed_loop=True,
                evidence_authority="genesis",
            ),
        )
    )
    registry.register(
        AdapterDescriptor(
            simulator_id="isaaclab",
            label="Optional Isaac Lab manager-based environment adapter",
            factory=IsaacLabSimulator,
            dependencies=(Dependency("isaaclab", "isaaclab"),),
            capabilities=BackendCapabilities(
                owns_physics=True,
                closed_loop=True,
                evidence_authority="isaaclab",
            ),
        )
    )
    registry.register(
        AdapterDescriptor(
            simulator_id="external_command",
            label="External JSON-line simulator process",
            factory=ExternalCommandSimulator,
            capabilities=BackendCapabilities(
                closed_loop=True,
                evidence_authority="external_process",
            ),
        )
    )
    if discover_external:
        registry.discover()
    return registry
