from __future__ import annotations

import pytest

from benchstudio.campaigns import compile_campaign_spec


def test_campaign_spec_compiles_to_frozen_plan():
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "temporal-transfer"},
            "task": {"task_id": "arrange"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {
                "seeds": [100, 101],
                "paired": True,
                "conditions": [{"denoising_steps": 2, "action_prefix": 5}],
            },
        }
    )
    assert plan.run_id == "temporal-transfer"
    assert len(plan.attempts) == 2
    assert len(plan.source_spec_sha256) == 64


def test_campaign_spec_rejects_unpaired_design():
    with pytest.raises(ValueError, match="paired"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "run"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {"seeds": [1], "paired": False, "conditions": [{"x": 1}]},
            }
        )


def test_campaign_spec_rejects_unauthorized_enabled_physical_environment():
    with pytest.raises(ValueError, match="authorization"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "run"},
                "task": {"task_id": "task"},
                "environments": [
                    {"id": "robot", "kind": "physical", "enabled": True},
                ],
                "evaluation": {"seeds": [1], "paired": True, "conditions": [{"x": 1}]},
            }
        )


def test_campaign_spec_rejects_physical_automatic_retry():
    with pytest.raises(ValueError, match="automatic retries"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "physical"},
                "task": {"task_id": "task"},
                "environments": [
                    {
                        "id": "robot",
                        "kind": "physical",
                        "enabled": True,
                        "requires_authorization": True,
                        "retry_policy": "automatic",
                    }
                ],
                "evaluation": {"seeds": [1], "paired": True, "conditions": [{"x": 1}]},
            }
        )


def test_campaign_spec_rejects_unknown_execution_strategy():
    with pytest.raises(ValueError, match="execution_strategy"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "bad-strategy"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "execution_strategy": "unknown",
                    "conditions": [{"x": 1}],
                },
            }
        )


def test_campaign_spec_rejects_non_frozen_confirmation_or_imputed_missingness():
    base = {
        "schema": "benchstudio.campaign.v1",
        "experiment": {"name": "run"},
        "task": {"task_id": "task"},
        "environments": [{"id": "sim", "kind": "simulator"}],
        "evaluation": {
            "seeds": [1],
            "paired": True,
            "conditions": [{"x": 1}],
        },
    }
    for field, value in (("confirmation_plan", "adaptive"), ("missing_outcomes", "impute")):
        spec = {**base, "evaluation": {**base["evaluation"], field: value}}
        with pytest.raises(ValueError, match=field):
            compile_campaign_spec(spec)


def test_campaign_spec_rejects_unpinned_model_checkpoint():
    with pytest.raises(ValueError, match="model.checkpoint"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "run"},
                "model": {"adapter": "mock", "checkpoint": "latest"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {"seeds": [1], "paired": True, "conditions": [{"x": 1}]},
            }
        )


def test_campaign_spec_freezes_enabled_environment_identity_and_protocol():
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "sim-real", "protocol_revision": "v1"},
            "model": {"adapter": "mock", "checkpoint": "sha256:" + "a" * 64},
            "task": {"task_id": "pick", "task_revision": "rev-1"},
            "environments": [
                {"id": "sim", "kind": "simulator"},
                {"id": "real", "kind": "physical", "enabled": False},
            ],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"id": "baseline", "action_prefix": 2}],
            },
        }
    )
    assert len(plan.attempts) == 1
    assert plan.attempts[0].key.environment_id == "sim"
    assert plan.protocol["S"]["task"]["task_revision"] == "rev-1"


def test_campaign_spec_expands_enabled_multiple_environments():
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "paired"},
            "task": {"task_id": "pick"},
            "environments": [
                {"id": "sim", "kind": "simulator"},
                {"id": "shadow", "kind": "simulator", "enabled": True},
            ],
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"id": "baseline"}],
            },
        }
    )
    assert [attempt.key.environment_id for attempt in plan.attempts] == ["sim", "shadow"]
    assert plan.attempts[0].key.pair_id == plan.attempts[1].key.pair_id


def test_campaign_spec_rejects_resource_budget_before_execution():
    with pytest.raises(ValueError, match="max_attempts"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "budgeted"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1, 2],
                    "paired": True,
                    "conditions": [{"id": "a"}, {"id": "b"}],
                    "resource_budget": {"max_attempts": 2},
                },
            }
        )


def test_campaign_spec_rejects_unknown_resource_budget_field():
    with pytest.raises(ValueError, match="unsupported resource budget"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "budgeted"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "conditions": [{"id": "a"}],
                    "resource_budget": {"gpu_hours": 1},
                },
            }
        )


def test_campaign_spec_rejects_incompatible_model_execution_strategy():
    with pytest.raises(ValueError, match="requires supports_async"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "capability-gated"},
                "model": {
                    "adapter": "mock",
                    "capabilities": {
                        "model_id": "m",
                        "family": "vla",
                        "input_modalities": ["image"],
                        "output_representation": "joint_targets",
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
                    "execution_strategy": "async",
                    "conditions": [{"action_prefix": 1}],
                },
            }
        )
