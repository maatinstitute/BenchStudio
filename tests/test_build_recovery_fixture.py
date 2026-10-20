import json

from scripts.build_recovery_fixture import bind_pair, prepare_probe


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_recovery_fixture_binds_failed_and_recovered_attempts(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "scenario.yaml").write_text(
        "runtime:\n  max_episode_steps: 400\n", encoding="utf-8"
    )
    (source / "asset.txt").write_text("fixture", encoding="utf-8")
    (source / "waypoints.json").write_text('{"waypoints": []}', encoding="utf-8")
    probe = tmp_path / "probe"

    prepare_probe(source, probe, 125)

    prepared = (probe / "scenario.yaml").read_text(encoding="utf-8")
    intervention = json.loads(
        (probe / "recovery-intervention.json").read_text(encoding="utf-8")
    )
    assert "  max_episode_steps: 125" in prepared
    assert intervention["failed_value"] == 125
    assert intervention["recovered_value"] == 400
    assert intervention["policy_changed"] is False

    run_root = tmp_path / "run"
    failed_dir = run_root / "recovery" / "episode-2" / "attempt-0"
    recovered_dir = run_root / "recovery" / "episode-2" / "attempt-1"
    _write_json(
        failed_dir / "report.json",
        {"success": False, "stop_reason": "max_steps", "steps": 125, "sim_time_s": 2.5},
    )
    _write_json(
        recovered_dir / "report.json",
        {"success": True, "stop_reason": "success", "steps": 235, "sim_time_s": 4.7},
    )
    for directory in (failed_dir, recovered_dir):
        (directory / "trace.ndjson").write_text("{}\n", encoding="utf-8")
        (directory / "episode.mp4").write_bytes(b"video")
    manifest = run_root / "manifests" / "episode-2.json"
    _write_json(manifest, {"episode_index": 2, "seed": 43})

    output = run_root / "recovery.json"
    bind_pair(
        output=output,
        episode_index=2,
        manifest_path=manifest,
        intervention_path=probe / "recovery-intervention.json",
        failed_dir=failed_dir,
        recovered_dir=recovered_dir,
        failed_policy_path=probe / "waypoints.json",
        recovered_policy_path=source / "waypoints.json",
    )

    recovery = json.loads(output.read_text(encoding="utf-8"))
    assert recovery["status"] == "recovered"
    assert recovery["seed"] == 43
    assert recovery["policy_binding"]["unchanged"] is True
    assert recovery["policy_binding"]["failed_attempt_sha256"] == (
        recovery["policy_binding"]["recovered_attempt_sha256"]
    )
    assert [attempt["success"] for attempt in recovery["attempts"]] == [False, True]
    assert recovery["attempts"][0]["files"]["episode.mp4"]["sha256"]
    assert recovery["attempts"][1]["files"]["trace.ndjson"]["path"] == (
        "recovery/episode-2/attempt-1/trace.ndjson"
    )
