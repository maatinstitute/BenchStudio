import json

from scripts.build_recovery_fixture import bind_pair, prepare_probe


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_recovery_fixture_preserves_failed_intervention_pair(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "scenario.yaml").write_text("runtime: {}\n", encoding="utf-8")
    (source / "asset.txt").write_text("fixture", encoding="utf-8")
    _write_json(
        source / "waypoints.json",
        {
            "waypoints": [
                {"label": "approach", "time_s": 1.2},
                {"label": "descend", "time_s": 2.4},
                {"label": "close on contact", "time_s": 3.0},
                {"label": "lift", "time_s": 4.8},
            ]
        },
    )
    probe = tmp_path / "probe"

    prepare_probe(source, probe, 2.4)

    prepared = json.loads((probe / "waypoints.json").read_text(encoding="utf-8"))
    intervention = json.loads(
        (probe / "intervention.json").read_text(encoding="utf-8")
    )
    assert [waypoint["time_s"] for waypoint in prepared["waypoints"]] == [
        1.2,
        3.6,
        4.2,
        6.0,
    ]
    assert intervention["baseline_value"] == 1.2
    assert intervention["intervention_value"] == 2.4
    assert intervention["policy_changed"] is True

    run_root = tmp_path / "run"
    failed_dir = run_root / "recovery" / "episode-2" / "attempt-0"
    recovered_dir = run_root / "recovery" / "episode-2" / "attempt-1"
    _write_json(
        failed_dir / "report.json",
        {"success": False, "stop_reason": "max_steps", "steps": 125, "sim_time_s": 2.5},
    )
    _write_json(
        recovered_dir / "report.json",
        {"success": False, "stop_reason": "max_steps", "steps": 400, "sim_time_s": 8.0},
    )
    for directory in (failed_dir, recovered_dir):
        (directory / "trace.ndjson").write_text("{}\n", encoding="utf-8")
        (directory / "episode.mp4").write_bytes(b"video")
        _write_json(
            directory / "contact-analysis.json",
            {"failure_class": "transient_impact_ejected_object"},
        )
    manifest = run_root / "manifests" / "episode-2.json"
    _write_json(manifest, {"episode_index": 2, "seed": 43})

    output = run_root / "recovery.json"
    bind_pair(
        output=output,
        episode_index=2,
        manifest_path=manifest,
        intervention_path=probe / "intervention.json",
        failed_dir=failed_dir,
        recovered_dir=recovered_dir,
        failed_policy_path=source / "waypoints.json",
        recovered_policy_path=probe / "waypoints.json",
    )

    recovery = json.loads(output.read_text(encoding="utf-8"))
    assert recovery["status"] == "lift_still_failed"
    assert recovery["seed"] == 43
    assert recovery["policy_binding"]["unchanged"] is False
    assert recovery["policy_binding"]["failed_attempt_sha256"] != (
        recovery["policy_binding"]["recovered_attempt_sha256"]
    )
    assert [attempt["success"] for attempt in recovery["attempts"]] == [False, False]
    assert recovery["attempts"][0]["files"]["episode.mp4"]["sha256"]
    assert recovery["attempts"][1]["files"]["contact-analysis.json"]["sha256"]
    assert recovery["attempts"][1]["files"]["trace.ndjson"]["path"] == (
        "recovery/episode-2/attempt-1/trace.ndjson"
    )
