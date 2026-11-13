from __future__ import annotations

import json

import pytest

from ival.campaigns import CampaignPlanner, load_frozen_campaign_plan, shard_attempt_ids


def _plan():
    return CampaignPlanner(
        run_id="cluster-run",
        scenario_id="task",
        conditions=[{"denoising_steps": 2, "action_prefix": 1}],
        seeds=range(7),
    ).freeze()


def test_frozen_plan_shards_are_deterministic_disjoint_and_complete(tmp_path):
    plan = _plan()
    path = tmp_path / "plan.json"
    plan.write(path)
    reloaded = load_frozen_campaign_plan(path)

    shards = [shard_attempt_ids(reloaded, shard_index=index, shard_count=3) for index in range(3)]
    assert shards == [
        ("attempt-000000", "attempt-000003", "attempt-000006"),
        ("attempt-000001", "attempt-000004"),
        ("attempt-000002", "attempt-000005"),
    ]
    assert set().union(*map(set, shards)) == {
        attempt.key.attempt_id for attempt in plan.attempts
    }
    assert sum(map(len, shards)) == len(plan.attempts)


@pytest.mark.parametrize(
    ("index", "count"),
    [(-1, 2), (2, 2), (0, 0), (0, 8), (True, 2), (0, True)],
)
def test_frozen_plan_shards_reject_invalid_coordinates(index, count):
    with pytest.raises(ValueError):
        shard_attempt_ids(_plan(), shard_index=index, shard_count=count)


def test_sharding_does_not_change_serialized_plan(tmp_path):
    plan = _plan()
    before = json.dumps(plan.to_dict(), sort_keys=True)
    shard_attempt_ids(plan, shard_index=1, shard_count=3)
    assert json.dumps(plan.to_dict(), sort_keys=True) == before
