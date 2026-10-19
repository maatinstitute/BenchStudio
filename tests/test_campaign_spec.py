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


def test_campaign_spec_rejects_non_string_execution_strategy():
    with pytest.raises(ValueError, match="execution_strategy"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "bad-strategy-type"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "execution_strategy": [],
                    "conditions": [{"x": 1}],
                },
            }
        )


def test_strategy_type_error_is_rejected_before_model_capability_binding():
    with pytest.raises(ValueError, match="execution_strategy"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "bad-strategy-profile"},
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
                    "execution_strategy": [],
                    "conditions": [{"x": 1}],
                },
            }
        )


@pytest.mark.parametrize("repetitions", [0, -1, 1.5, True])
def test_campaign_spec_rejects_invalid_repetition_counts(repetitions):
    with pytest.raises(ValueError, match="evaluation.repetitions"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "invalid-repetitions"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "repetitions": repetitions,
                    "conditions": [{"x": 1}],
                },
            }
        )


@pytest.mark.parametrize(
    "condition, message",
    [
        ({"action_prefix": "2"}, "action_prefix"),
        ({"observation_refresh_ticks": 0}, "observation_refresh_ticks"),
        ({"max_episode_steps": True}, "max_episode_steps"),
        ({"denoising_steps": -1}, "denoising_steps"),
        ({"execution_strategy": []}, "execution_strategy"),
        ({"max_cache_entries": 0}, "max_cache_entries"),
        ({"id": 42}, r"conditions\[0\]\.id"),
    ],
)
def test_campaign_spec_rejects_invalid_condition_controls(condition, message):
    with pytest.raises(ValueError, match=message):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "invalid-condition"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "conditions": [condition],
                },
            }
        )


@pytest.mark.parametrize("seeds", [[True], [1.5], ["1"]])
def test_campaign_spec_rejects_non_integer_seeds(seeds):
    with pytest.raises(ValueError, match="evaluation.seeds"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "invalid-seeds"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": seeds,
                    "paired": True,
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


@pytest.mark.parametrize("field", ["input_modalities", "supported_metrics"])
def test_campaign_spec_rejects_scalar_model_capability_sequences(field):
    capabilities = {
        "model_id": "typed",
        "family": "custom",
        "input_modalities": ["state"],
        "output_representation": "action_chunk",
        "supports_closed_loop": True,
        "supports_action_chunks": True,
        "supported_metrics": ["success"],
    }
    capabilities[field] = "state" if field == "input_modalities" else "success"
    with pytest.raises(ValueError, match=f"model.capabilities.{field}"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "typed-capabilities"},
                "model": {"adapter": "mock", "capabilities": capabilities},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "conditions": [{"x": 1}],
                },
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


def test_campaign_spec_freezes_worldepisode_binding_for_executor_preflight():
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "worldepisode-spec"},
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "worldepisode": {
                "record": {
                    "schema": "worldepisode",
                    "episode": {"episode_id": "episode-1"},
                    "world_revision": {"world_revision_id": "rev-1"},
                },
                "expected_episode_id": "episode-1",
                "expected_revision_id": "rev-1",
            },
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "conditions": [{"id": "baseline", "action_prefix": 1}],
            },
        }
    )
    assert plan.protocol["worldepisode"]["expected_episode_id"] == "episode-1"


def test_campaign_spec_rejects_malformed_worldepisode_binding():
    base = {
        "schema": "benchstudio.campaign.v1",
        "experiment": {"name": "bad-worldepisode"},
        "task": {"task_id": "task"},
        "environments": [{"id": "sim", "kind": "simulator"}],
        "evaluation": {"seeds": [1], "paired": True, "conditions": [{"x": 1}]},
    }
    with pytest.raises(ValueError, match="worldepisode.record"):
        compile_campaign_spec({**base, "worldepisode": {"record": []}})
    with pytest.raises(ValueError, match="expected_episode_id"):
        compile_campaign_spec(
            {
                **base,
                "worldepisode": {
                    "record": {"schema": "worldepisode"},
                    "expected_episode_id": 1,
                },
            }
        )


def test_campaign_spec_freezes_execution_semantics_in_protocol_envelope():
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "execution-envelope"},
            "task": {"task_id": "task"},
            "environments": [{"id": "sim", "kind": "simulator"}],
            "execution": {
                "clock_domains": ["sim_time", "host_monotonic"],
                "queue_capacity": 8,
                "controller_deadline_ns": 1000000,
            },
            "evaluation": {
                "seeds": [1],
                "paired": True,
                "execution_strategy": "cached",
                "max_cache_entries": 32,
                "conditions": [{"id": "baseline", "action_prefix": 3, "max_episode_steps": 20}],
            },
        }
    )
    execution = plan.protocol["X"]
    assert execution["clock_domains"] == ["sim_time", "host_monotonic"]
    assert execution["queue_capacity"] == 8
    assert execution["strategy"] == "cached"
    assert execution["max_cache_entries"] == 32
    assert execution["condition_controls"] == [
        {"id": "baseline", "action_prefix": 3, "max_episode_steps": 20}
    ]


def test_campaign_spec_rejects_malformed_execution_semantics():
    base = {
        "schema": "benchstudio.campaign.v1",
        "experiment": {"name": "bad-execution"},
        "task": {"task_id": "task"},
        "environments": [{"id": "sim", "kind": "simulator"}],
        "evaluation": {"seeds": [1], "paired": True, "conditions": [{"x": 1}]},
    }
    with pytest.raises(ValueError, match="clock_domains"):
        compile_campaign_spec({**base, "execution": {"clock_domains": []}})
    with pytest.raises(ValueError, match="queue_capacity"):
        compile_campaign_spec({**base, "execution": {"queue_capacity": -1}})


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


def test_campaign_spec_rejects_incompatible_condition_execution_strategy():
    with pytest.raises(ValueError, match="execution_strategy async requires supports_async"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "condition-capability-gated"},
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
                    "conditions": [{"execution_strategy": "async"}],
                },
            }
        )


def test_campaign_spec_rejects_malformed_frozen_adapter_configuration():
    base = {
        "schema": "benchstudio.campaign.v1",
        "experiment": {"name": "malformed"},
        "model": {"adapter": "mock"},
        "task": {"task_id": "task"},
        "environments": [{"id": "sim", "kind": "simulator"}],
        "evaluation": {"seeds": [1], "paired": True, "conditions": [{"x": 1}]},
    }
    with pytest.raises(ValueError, match="model.adapter_config"):
        compile_campaign_spec({**base, "model": {"adapter": "mock", "adapter_config": []}})
    with pytest.raises(ValueError, match="scenario_pack_digest"):
        compile_campaign_spec(
            {**base, "task": {"task_id": "task", "scenario_pack_digest": "latest"}}
        )
    with pytest.raises(ValueError, match="adapter_config"):
        compile_campaign_spec(
            {
                **base,
                "environments": [{"id": "sim", "kind": "simulator", "adapter_config": "latest"}],
            }
        )


def test_campaign_spec_accepts_pinned_scenario_revision_and_digest():
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "pinned"},
            "task": {
                "task_id": "task",
                "task_revision": "rev-1",
                "scenario_pack_digest": "sha256:" + "a" * 64,
            },
            "environments": [{"id": "sim", "kind": "simulator"}],
            "evaluation": {"seeds": [1], "paired": True, "conditions": [{"x": 1}]},
        }
    )
    assert plan.protocol["S"]["task"]["task_revision"] == "rev-1"
