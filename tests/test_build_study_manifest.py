from scripts.build_study_manifest import build_manifest


def test_study_manifest_freezes_one_hundred_deterministic_episode_identities():
    study = {
        "study_id": "industrial-preflight-v1",
        "episodes_per_simulator": 100,
        "randomization": {
            "cube_position_jitter_m": [0.012, 0.012, 0.0],
            "cube_yaw_jitter_rad": 0.2,
        },
    }
    first = build_manifest(study)
    second = build_manifest(study)

    assert first == second
    assert first["episode_count"] == 100
    assert len(first["episodes"]) == 100
    assert first["episodes"][0]["episode_id"] == "episode-000"
    assert first["episodes"][-1]["episode_id"] == "episode-099"
    assert len({row["seed"] for row in first["episodes"]}) == 100
    assert all(row["status"] == "not_scheduled" for row in first["episodes"])
    assert first["manifest_sha256"]
