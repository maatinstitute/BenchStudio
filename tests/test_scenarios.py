from __future__ import annotations

import pytest

from benchstudio.campaigns import CampaignPlanner
from benchstudio.scenarios import ScenarioPack, load_scenario_pack, validate_scenario_pack


def test_scenario_pack_is_content_addressed(tmp_path):
    pack = ScenarioPack.create(
        scenario_id="arrange",
        task_revision="rev-1",
        asset_digests_sha256=["a" * 64],
        initial_condition_digest_sha256="b" * 64,
        success_criterion_version="success-v1",
    )
    assert validate_scenario_pack(pack) == []
    path = tmp_path / "scenario-pack.json"
    pack.write(path)
    assert load_scenario_pack(path) == pack
    changed = ScenarioPack(**{**pack.to_dict(), "task_revision": "rev-2"})
    assert "pack_digest_sha256 does not match content" in validate_scenario_pack(changed)


def test_scenario_pack_digest_changes_pair_identity():
    first = CampaignPlanner(
        run_id="run",
        scenario_id="task",
        conditions=[{"x": 1}],
        seeds=[1],
        scenario_pack_digest="a" * 64,
    ).freeze()
    second = CampaignPlanner(
        run_id="run",
        scenario_id="task",
        conditions=[{"x": 1}],
        seeds=[1],
        scenario_pack_digest="b" * 64,
    ).freeze()
    assert first.attempts[0].key.pair_id != second.attempts[0].key.pair_id


def test_invalid_scenario_pack_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"scenario_id":"task"}')
    with pytest.raises((TypeError, ValueError)):
        load_scenario_pack(path)
