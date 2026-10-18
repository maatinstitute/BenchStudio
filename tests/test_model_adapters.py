from __future__ import annotations

import pytest

from benchstudio.campaigns import compile_campaign_spec
from benchstudio.contracts import ModelCapabilityProfile
from benchstudio.mock import MockPolicy
from benchstudio.model_adapters import (
    ModelAdapterDescriptor,
    ModelAdapterRegistry,
    ModelDependency,
    default_model_registry,
)


def test_default_model_registry_is_ready():
    readiness = default_model_registry(discover_external=False).readiness("mock")
    assert readiness["ready"] is True
    assert readiness["capabilities"].model_id == "mock_policy"
    assert readiness["capabilities"].to_dict()["input_modalities"] == ["state"]


def test_default_model_registry_exposes_external_command_policy():
    registry = default_model_registry(discover_external=False)
    descriptor = registry.get("external_command")
    assert descriptor.capabilities.supports_closed_loop is True
    assert registry.readiness("external_command")["ready"] is True


def test_default_model_registry_exposes_persistent_external_command_policy():
    registry = default_model_registry(discover_external=False)
    assert registry.readiness("persistent_external_command")["ready"] is True
    assert (
        "persistent_process"
        in registry.get("persistent_external_command").capabilities.runtime_controls
    )


def test_default_model_registry_exposes_named_vla_protocol_bridges():
    registry = default_model_registry(discover_external=False)
    for adapter_id in ("smolvla", "opendm"):
        descriptor = registry.get(adapter_id)
        assert registry.readiness(adapter_id)["ready"] is True
        assert descriptor.capabilities.family == "vla"
        assert descriptor.capabilities.supports_variable_action_horizon is True


def test_default_model_registry_exposes_digest_bound_trace_policy():
    registry = default_model_registry(discover_external=False)
    descriptor = registry.get("trace")
    assert registry.readiness("trace")["ready"] is True
    assert "digest_bound_observations" in descriptor.capabilities.runtime_controls


def test_model_registry_reports_missing_dependency():
    registry = ModelAdapterRegistry()
    registry.register(
        ModelAdapterDescriptor(
            "missing",
            "Missing model",
            MockPolicy,
            ModelCapabilityProfile(
                model_id="missing",
                family="custom",
                input_modalities=("state",),
                output_representation="action_chunk",
                supports_closed_loop=True,
                supports_action_chunks=True,
                supported_metrics=("success",),
            ),
            dependencies=(ModelDependency("missing", "benchstudio_missing_model_package"),),
        )
    )
    assert registry.readiness("missing")["ready"] is False
    with pytest.raises(RuntimeError, match="missing"):
        registry.create("missing")


def test_model_registry_readiness_reports_dependency_version(monkeypatch):
    import benchstudio.model_adapters as model_adapters

    monkeypatch.setattr(model_adapters.metadata, "version", lambda _name: "1.2.3")
    registry = ModelAdapterRegistry()
    registry.register(
        ModelAdapterDescriptor(
            "versioned",
            "Versioned model",
            MockPolicy,
            ModelCapabilityProfile(
                model_id="versioned",
                family="custom",
                input_modalities=("state",),
                output_representation="action_chunk",
                supports_closed_loop=True,
                supports_action_chunks=True,
                supported_metrics=("success",),
            ),
            dependencies=(ModelDependency("json", "json"),),
        )
    )
    readiness = registry.readiness("versioned")
    assert readiness["ready"] is True
    assert readiness["dependencies"][0]["version"] == "1.2.3"


def test_model_registry_readiness_reports_broken_optional_import(monkeypatch):
    registry = ModelAdapterRegistry()
    registry.register(
        ModelAdapterDescriptor(
            "broken",
            "Broken model",
            MockPolicy,
            ModelCapabilityProfile(
                model_id="broken",
                family="custom",
                input_modalities=("state",),
                output_representation="action_chunk",
                supports_closed_loop=True,
                supports_action_chunks=True,
                supported_metrics=("success",),
            ),
            dependencies=(ModelDependency("broken", "broken"),),
        )
    )
    monkeypatch.setattr(
        "benchstudio.model_adapters._module_available",
        lambda _name: (_ for _ in ()).throw(ImportError("transitive dependency missing")),
    )
    readiness = registry.readiness("broken")
    assert readiness["ready"] is False
    assert readiness["dependencies"][0]["error"] == ("ImportError: transitive dependency missing")


def test_model_registry_rejects_invalid_capability_profile():
    with pytest.raises(ValueError, match="invalid capabilities"):
        ModelAdapterRegistry().register(
            ModelAdapterDescriptor(
                "invalid",
                "Invalid",
                MockPolicy,
                ModelCapabilityProfile(
                    model_id="invalid",
                    family="custom",
                    input_modalities=(),
                    output_representation="action_chunk",
                    supports_closed_loop=True,
                    supports_action_chunks=False,
                    supported_metrics=(),
                ),
            )
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"family": "unknown"},
        {"supports_closed_loop": "yes"},
        {"inference_granularity": "unknown"},
        {"input_modalities": [""]},
        {"memory_bytes": 1.5},
    ],
)
def test_model_registry_rejects_malformed_capability_types(overrides):
    profile = ModelCapabilityProfile(
        model_id="typed",
        family="custom",
        input_modalities=("state",),
        output_representation="action_chunk",
        supports_closed_loop=True,
        supports_action_chunks=True,
        supported_metrics=("success",),
    )
    invalid = {**profile.__dict__, **overrides}
    with pytest.raises(ValueError, match="invalid capabilities"):
        ModelAdapterRegistry().register(
            ModelAdapterDescriptor("typed", "Typed", MockPolicy, ModelCapabilityProfile(**invalid))
        )


def test_model_registry_gates_declared_execution_strategy():
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "async-model"},
            "model": {"adapter": "mock"},
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "execution_strategy": "async",
                "conditions": [{"x": 1}],
            },
        }
    )
    assert default_model_registry(discover_external=False).validate_plan(plan) == (
        "model adapter mock does not support async execution",
    )


def test_model_registry_binds_declared_capabilities_to_adapter():
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "capability-binding"},
            "model": {
                "adapter": "mock",
                "capabilities": {
                    "model_id": "different-policy",
                    "family": "custom",
                    "input_modalities": ["state"],
                    "output_representation": "action_chunk",
                    "supports_closed_loop": True,
                    "supports_action_chunks": True,
                    "supported_metrics": ["success"],
                },
            },
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"x": 1}],
            },
        }
    )
    assert default_model_registry(discover_external=False).validate_plan(plan) == (
        "model adapter mock capability mismatch: model_id",
    )
