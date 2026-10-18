from __future__ import annotations

import pytest

from benchstudio.campaigns import compile_balanced_paired_plan


def test_balanced_paired_design_keeps_conditions_in_matched_blocks():
    plan = compile_balanced_paired_plan(
        run_id="paired-1",
        scenario_id="libero",
        suites=["spatial"],
        task_ids=[1],
        initial_state_ids=[10, 11],
        policy_seeds=[2000],
        conditions=[
            {"action_prefix": 1, "denoising_steps": 10},
            {"action_prefix": 5, "denoising_steps": 2},
        ],
    )
    assert len(plan.attempts) == 4
    blocks = {}
    for row in plan.paired_schedule:
        blocks.setdefault(row["block_id"], []).append(row)
    assert all(len(rows) == 2 for rows in blocks.values())
    assert all(len({row["pair_id"] for row in rows}) == 1 for rows in blocks.values())
    assert len({row["pair_id"] for row in plan.paired_schedule}) == 2


def test_balanced_paired_design_rejects_duplicate_conditions():
    with pytest.raises(ValueError, match="duplicate conditions"):
        compile_balanced_paired_plan(
            run_id="run",
            scenario_id="task",
            suites=["suite"],
            task_ids=[1],
            initial_state_ids=[1],
            policy_seeds=[1],
            conditions=[{"x": 1}, {"x": 1}],
        )
