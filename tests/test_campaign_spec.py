from __future__ import annotations

import pytest

from benchstudio.campaigns import compile_campaign_spec


def test_campaign_spec_compiles_to_frozen_plan():
    plan = compile_campaign_spec(
        {
            "schema": "benchstudio.campaign.v1",
            "experiment": {"name": "temporal-transfer"},
            "task": {"task_id": "arrange"},
            "evaluation": {
                "seeds": [100, 101],
                "paired": True,
                "conditions": [{"denoising_steps": 2, "action_prefix": 5}],
            },
        }
    )
    assert plan.run_id == "temporal-transfer"
    assert len(plan.attempts) == 2


def test_campaign_spec_rejects_unpaired_design():
    with pytest.raises(ValueError, match="paired"):
        compile_campaign_spec(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "run"},
                "task": {"task_id": "task"},
                "evaluation": {"seeds": [1], "paired": False, "conditions": [{"x": 1}]},
            }
        )
