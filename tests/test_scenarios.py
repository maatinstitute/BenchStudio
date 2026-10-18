from __future__ import annotations

import io
import zipfile

import pytest

from benchstudio.campaigns import CampaignPlanner
from benchstudio.scenarios import (
    ScenarioArchiveError,
    ScenarioPack,
    build_scenario_archive,
    extract_verified_scenario_archive,
    load_scenario_pack,
    scenario_archive_digest,
    validate_scenario_pack,
)


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


def test_scenario_archive_is_deterministic_and_excludes_scratch(tmp_path):
    root = tmp_path / "scenario"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "mesh.bin").write_bytes(b"mesh")
    (root / "scenario.json").write_text("{}\n")
    (root / "_run").mkdir()
    (root / "_run" / "scratch.txt").write_text("ignore")
    first = build_scenario_archive(root)
    second = build_scenario_archive(root)
    assert first == second
    assert scenario_archive_digest(first) == scenario_archive_digest(second)
    assert b"scratch.txt" not in first


def test_scenario_archive_verifies_and_rejects_traversal(tmp_path):
    root = tmp_path / "scenario"
    root.mkdir()
    (root / "task.json").write_text("{}")
    archive = build_scenario_archive(root)
    destination = tmp_path / "unpacked"
    digest = extract_verified_scenario_archive(
        archive, destination, expected_sha256=scenario_archive_digest(archive)
    )
    assert (destination / "task.json").is_file()
    assert len(digest) == 64

    with pytest.raises(ScenarioArchiveError, match="digest mismatch"):
        extract_verified_scenario_archive(archive, tmp_path / "wrong", expected_sha256="0" * 64)

    malicious = io.BytesIO()
    with zipfile.ZipFile(malicious, "w") as package:
        package.writestr("../escape.txt", "no")
    with pytest.raises(ScenarioArchiveError, match="unsafe path"):
        extract_verified_scenario_archive(malicious.getvalue(), tmp_path / "unsafe")
