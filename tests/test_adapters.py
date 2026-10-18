from __future__ import annotations

import pytest

from benchstudio.adapters import AdapterDescriptor, AdapterRegistry, Dependency, default_registry
from benchstudio.mock import MockSimulator


def test_default_registry_is_ready_without_optional_simulators():
    readiness = default_registry().readiness("mock")
    assert readiness["ready"] is True


def test_registry_reports_missing_dependency_without_importing_backend():
    registry = AdapterRegistry()
    registry.register(
        AdapterDescriptor(
            simulator_id="missing",
            label="Missing backend",
            factory=MockSimulator,
            dependencies=(Dependency("not-installed", "benchstudio_package_that_does_not_exist"),),
        )
    )
    readiness = registry.readiness("missing")
    assert readiness["ready"] is False
    assert readiness["missing_required"] == ["not-installed"]
    with pytest.raises(RuntimeError, match="not-installed"):
        registry.create("missing")


def test_duplicate_adapter_registration_is_rejected():
    registry = default_registry()
    with pytest.raises(ValueError, match="already registered"):
        registry.register(AdapterDescriptor("mock", "duplicate", MockSimulator))
