from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Callable

from .contracts import Simulator


@dataclass(frozen=True)
class Dependency:
    name: str
    import_name: str
    required: bool = True
    scope: str = "runtime"


@dataclass(frozen=True)
class AdapterDescriptor:
    simulator_id: str
    label: str
    factory: Callable[..., Simulator]
    dependencies: tuple[Dependency, ...] = field(default_factory=tuple)


class AdapterRegistry:
    """Explicit simulator registry with dependency-aware readiness reporting."""

    def __init__(self) -> None:
        self._descriptors: dict[str, AdapterDescriptor] = {}

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
            dependencies.append(
                {
                    "name": dependency.name,
                    "import_name": dependency.import_name,
                    "available": available,
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
        }

    def create(self, simulator_id: str, **kwargs: Any) -> Simulator:
        descriptor = self.get(simulator_id)
        readiness = self.readiness(simulator_id)
        if not readiness["ready"]:
            missing = ", ".join(readiness["missing_required"])
            raise RuntimeError(f"simulator {simulator_id} is not ready; missing: {missing}")
        return descriptor.factory(**kwargs)


def module_available(import_name: str) -> bool:
    try:
        importlib.import_module(import_name)
    except ModuleNotFoundError as exc:
        if exc.name == import_name or import_name.startswith(f"{exc.name}."):
            return False
        raise
    return True


def default_registry() -> AdapterRegistry:
    from .mock import MockSimulator

    registry = AdapterRegistry()
    registry.register(
        AdapterDescriptor(
            simulator_id="mock",
            label="Deterministic mock simulator",
            factory=MockSimulator,
        )
    )
    return registry
