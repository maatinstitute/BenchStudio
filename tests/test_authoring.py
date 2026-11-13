from __future__ import annotations

import json

import pytest

from benchstudio.authoring import PairedStudy, condition_grid, simulator_environment


def test_condition_grid_compiles_to_paired_frozen_plan(tmp_path):
    conditions = condition_grid(denoising_steps=[2, 5], action_prefix=[2, 5])
    study = PairedStudy(
        name="refinement-refresh",
        task_id="held-out-task",
        conditions=conditions,
        seeds=(11, 12),
        environments=(simulator_environment("libero"),),
        resource_budget={"max_attempts": 8},
    )

    source = tmp_path / "study.json"
    study.write_spec(source)
    plan = study.freeze()

    assert len(conditions) == 4
    assert len(plan.attempts) == 8
    assert len({attempt.key.pair_id for attempt in plan.attempts}) == 2
    assert {attempt.metadata["condition"]["id"] for attempt in plan.attempts} == {
        "denoising_steps=2,action_prefix=2",
        "denoising_steps=2,action_prefix=5",
        "denoising_steps=5,action_prefix=2",
        "denoising_steps=5,action_prefix=5",
    }
    assert json.loads(source.read_text())["evaluation"]["paired"] is True
    assert plan.source_spec_sha256 == study.freeze().source_spec_sha256


def test_authoring_cannot_override_paired_design_controls():
    study = PairedStudy(
        name="invalid",
        task_id="task",
        conditions=({"effort": 1},),
        seeds=(1,),
        evaluation_options={"paired": False},
    )
    with pytest.raises(ValueError, match="cannot replace"):
        study.freeze()


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({}, "at least one factor"),
        ({"effort": []}, "at least one level"),
        ({"effort": "low"}, "iterable of levels"),
    ],
)
def test_condition_grid_rejects_ambiguous_factors(kwargs, message):
    with pytest.raises(ValueError, match=message):
        condition_grid(**kwargs)


def test_physical_execution_is_not_exposed_as_an_authoring_shortcut():
    assert simulator_environment("sim")["kind"] == "simulator"
