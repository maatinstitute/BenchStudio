from __future__ import annotations

import pytest

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
