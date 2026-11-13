from ival.analysis.alpabridge_review import (
    critical_event_bundle,
    frame_bookmarks,
    has_intervention,
    paired_bookmarks,
    severity_policy,
)


def test_baseline_modes_are_not_interventions_but_corrections_are():
    for mode in ("constant_velocity", "route_following", "mpc_planner", "direct_actor_planner", "maintain"):
        assert not has_intervention({"step": {"action_mode": mode}})
    assert has_intervention({"step": {"action_mode": "nudge_left"}})
    assert has_intervention({"step": {"action_mode": "maintain", "intervention": True}})


def test_bookmarks_apply_profile_thresholds_and_stall_context():
    manifest = {"source": "alpasim", "scenario_cluster": "fresh_3scene"}
    frames = [
        {"frame_idx": 0, "timestamp_s": 0.0, "ego": {"speed": 0.0, "goal_distance": 10.0},
         "step": {"collision_risk": 0.7, "min_obstacle_distance": 0.4}, "trigger_state": {}},
        {"frame_idx": 1, "timestamp_s": 0.1, "ego": {"speed": 0.0, "goal_distance": 10.0}, "step": {}, "trigger_state": {}},
        {"frame_idx": 2, "timestamp_s": 0.2, "ego": {"speed": 0.0, "goal_distance": 10.0}, "step": {}, "trigger_state": {}},
        {"frame_idx": 3, "timestamp_s": 0.3, "ego": {"speed": 0.0, "goal_distance": 10.0}, "step": {}, "trigger_state": {}},
    ]
    bookmarks = frame_bookmarks(frames, manifest)
    assert severity_policy(manifest)["collision_risk_event_threshold"] == 0.65
    assert {item["kind"] for item in bookmarks} >= {"collision_risk_spike", "near_miss", "stall_or_deadlock"}
    bundle = critical_event_bundle(manifest, frames, min_severity="high")
    assert bundle["critical_frame_count"] == 4


def test_pairs_are_kind_matched_and_timestamp_sorted():
    left = [{"kind": "near_miss", "frame_idx": 1, "timestamp_s": 1.0}]
    right = [{"kind": "near_miss", "frame_idx": 8, "timestamp_s": 1.1}]
    assert paired_bookmarks(left, right)[0]["timestamp_delta_s"] == 0.1
