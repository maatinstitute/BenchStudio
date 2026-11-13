from __future__ import annotations

import io
import zipfile

import pytest

from reva.campaigns import CampaignPlanner
from reva.scenarios import (
    ScenarioArchiveError,
    ScenarioPack,
    build_scenario_archive,
    extract_verified_scenario_archive,
    load_scenario_pack,
    scenario_archive_digest,
    validate_scenario_pack,
    verify_scenario_archive,
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


def test_scenario_pack_rejects_non_hex_identity_digests():
    pack = ScenarioPack(
        scenario_id="task",
        task_revision="rev-1",
        asset_digests_sha256=("g" * 64,),
        initial_condition_digest_sha256="not-a-digest",
        success_criterion_version="success-v1",
        pack_digest_sha256="z" * 64,
    )
    issues = validate_scenario_pack(pack)
    assert "asset digests must be lowercase SHA-256 hex strings" in issues
    assert "initial_condition_digest_sha256 must be lowercase SHA-256 hex" in issues
    assert "pack_digest_sha256 must be lowercase SHA-256 hex" in issues


def test_scenario_pack_requires_success_criterion_version():
    pack = ScenarioPack(
        scenario_id="task",
        task_revision="rev-1",
        asset_digests_sha256=("a" * 64,),
        initial_condition_digest_sha256="b" * 64,
        success_criterion_version="",
        pack_digest_sha256="c" * 64,
    )
    assert "success_criterion_version is required" in validate_scenario_pack(pack)


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


def test_scenario_archive_can_be_verified_without_extraction(tmp_path):
    root = tmp_path / "scenario"
    root.mkdir()
    (root / "task.json").write_text("{}")
    archive = build_scenario_archive(root)
    result = verify_scenario_archive(archive, expected_sha256=scenario_archive_digest(archive))
    assert result["valid"] is True
    tampered = verify_scenario_archive(
        archive + b"x", expected_sha256=scenario_archive_digest(archive)
    )
    assert tampered["valid"] is False


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


def test_scenario_archive_rejects_symlinks_and_duplicate_entries(tmp_path):
    root = tmp_path / "scenario"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    (root / "linked.txt").symlink_to(outside)
    with pytest.raises(ScenarioArchiveError, match="symlink"):
        build_scenario_archive(root)

    duplicate = io.BytesIO()
    with zipfile.ZipFile(duplicate, "w") as package:
        package.writestr("task.json", "{}")
        package.writestr("task.json", "tampered")
    with pytest.raises(ScenarioArchiveError, match="duplicate"):
        extract_verified_scenario_archive(duplicate.getvalue(), tmp_path / "duplicate")


def test_scenario_archive_rejects_invalid_zip(tmp_path):
    with pytest.raises(ScenarioArchiveError, match="valid ZIP"):
        extract_verified_scenario_archive(b"not-a-zip", tmp_path / "invalid")
