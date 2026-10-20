import json

from scripts.build_pilot_variant import prepare_variant


def test_prepare_variant_changes_policy_timing_offset_and_horizon(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "waypoints.json").write_text(
        json.dumps({"waypoints": [
            {"label": "ready", "time_s": 0.0, "joints": {"shoulder_pan": 0.0}},
            {"label": "descend", "time_s": 2.0, "joints": {"shoulder_pan": 0.0}},
        ]}),
        encoding="utf-8",
    )
    (source / "scenario.yaml").write_text(
        "success:\n  timeout_sim_seconds: 8.0\nruntime:\n  max_episode_steps: 400\n",
        encoding="utf-8",
    )
    output = tmp_path / "variant"
    condition = prepare_variant(
        source,
        output,
        condition_id="fast",
        label="Fast",
        time_scale=0.5,
        shoulder_pan_offset_rad=0.2,
        max_episode_steps=250,
    )

    policy = json.loads((output / "waypoints.json").read_text(encoding="utf-8"))
    assert policy["waypoints"][0]["time_s"] == 0.0
    assert policy["waypoints"][0]["joints"]["shoulder_pan"] == 0.0
    assert policy["waypoints"][1]["time_s"] == 1.0
    assert policy["waypoints"][1]["joints"]["shoulder_pan"] == 0.2
    assert "timeout_sim_seconds: 5" in (output / "scenario.yaml").read_text()
    assert "max_episode_steps: 250" in (output / "scenario.yaml").read_text()
    assert condition["policy_sha256"]
