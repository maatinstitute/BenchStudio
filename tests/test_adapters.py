from __future__ import annotations

import pytest

from benchstudio.adapters import (
    AdapterDescriptor,
    AdapterRegistry,
    BackendCapabilities,
    Dependency,
    default_registry,
)
from benchstudio.mock import MockSimulator


def test_default_registry_is_ready_without_optional_simulators():
    readiness = default_registry(discover_external=False).readiness("mock")
    assert readiness["ready"] is True


def test_default_registry_declares_optional_mujoco_backend():
    descriptor = default_registry(discover_external=False).get("mujoco")
    assert descriptor.capabilities.owns_physics is True
    assert descriptor.dependencies[0].import_name == "mujoco"


def test_default_registry_declares_optional_gymnasium_backend():
    descriptor = default_registry(discover_external=False).get("gymnasium")
    assert descriptor.capabilities.closed_loop is True
    assert descriptor.capabilities.owns_physics is False


def test_trace_replay_backend_is_registered_and_instantiable():
    registry = default_registry()
    readiness = registry.readiness("trace_replay")
    assert readiness["ready"] is True
    simulator = registry.create("trace_replay", steps=2)
    assert simulator.simulator_id == "trace_replay_simulator"


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
    registry = default_registry(discover_external=False)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(AdapterDescriptor("mock", "duplicate", MockSimulator))


def test_external_discovery_is_optional_and_diagnostic():
    registry = default_registry(discover_external=False)
    assert registry.discover(group="benchstudio.no_such_group") == ()
    assert registry.discovery_diagnostics == ()


def test_backend_capabilities_are_reported_and_can_gate_creation():
    registry = AdapterRegistry()
    registry.register(
        AdapterDescriptor(
            simulator_id="physical",
            label="Physical test backend",
            factory=lambda: object(),
            capabilities=BackendCapabilities(
                owns_physics=True,
                owns_official_scoring=True,
                owns_hardware_safety=True,
                closed_loop=True,
                evidence_authority="partner",
            ),
        )
    )

    readiness = registry.readiness("physical")
    assert readiness["capabilities"]["owns_hardware_safety"] is True
    assert registry.capability_issues("physical", {"closed_loop": True}) == ()
    assert registry.capability_issues("physical", {"owns_physics": True}) == ()


def test_capability_gate_rejects_facade_for_physics_authority():
    registry = default_registry(discover_external=False)
    assert registry.capability_issues("mock", {"owns_physics": True}) == ("owns_physics",)
    with pytest.raises(RuntimeError, match="owns_physics"):
        registry.create("mock", required_capabilities={"owns_physics": True})


def test_registry_validates_backend_requirements_frozen_in_plan():
    plan = type(
        "Plan",
        (),
        {
            "protocol": {
                "S": {
                    "environments": [
                        {
                            "id": "sim",
                            "adapter": "mock",
                            "required_capabilities": {"owns_physics": True},
                        }
                    ]
                }
            }
        },
    )()
    registry = default_registry(discover_external=False)
    assert registry.validate_plan(plan) == ("sim: adapter mock lacks owns_physics",)


@pytest.mark.parametrize(
    ("environments", "expected"),
    [
        ("not-a-list", "protocol.S.environments must be a list"),
        (["not-a-mapping"], "environment declaration must be a mapping"),
        ([{"adapter": "mock"}], "environment declaration requires a non-empty string id"),
        ([{"id": "sim", "adapter": None}], "sim: adapter must be a non-empty string"),
        ([{"id": "sim", "adapter": "mock", "adapter_config": []}], "sim: adapter_config must be a mapping"),
        ([{"id": "sim", "adapter": "mock", "required_capabilities": []}], "sim: required_capabilities must be a mapping"),
        ([{"id": "sim", "adapter": "mock"}, {"id": "sim", "adapter": "mock"}], "duplicate environment id sim"),
    ],
)
def test_registry_rejects_malformed_environment_declarations(environments, expected):
    plan = type("Plan", (), {"protocol": {"S": {"environments": environments}}})()
    assert expected in default_registry(discover_external=False).validate_plan(plan)
