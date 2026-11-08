from __future__ import annotations

from benchstudio.integrations.alpasim_metrics import build_alpasim_evidence, load_alpasim_metrics


def test_imports_alpasim_aggregate_text_metrics(tmp_path):
    aggregate = tmp_path / "aggregate"
    aggregate.mkdir()
    (aggregate / "metrics_results.txt").write_text(
        "\n".join(
            [
                "Run: token_dagger_bc",
                "n_clips: 4, n_rollouts/clip: 2",
                "collision_at_fault        0.00 ± 0.00      MAX",
                "offroad                   0.01 ± 0.00      MAX",
                "dist_to_gt_trajectory     2.40 ± 0.50      MAX",
                "safety_monitor_triggered  0.00 ± 0.00      MAX",
            ]
        ),
        encoding="utf-8",
    )
    metrics_path, metrics, run_count = load_alpasim_metrics(tmp_path)
    evidence = build_alpasim_evidence(tmp_path).to_dict()
    assert metrics_path.name == "metrics_results.txt"
    assert run_count == 8
    assert metrics["collision_at_fault"] == 0.0
    assert evidence["sensor_realistic"] is True
    assert evidence["official_policy_benchmark_score"] is False
    assert evidence["gates"]["collision_rate"] is True
    assert evidence["gates"]["route_deviation_m"] is True


def test_imports_json_and_csv_metrics(tmp_path):
    json_file = tmp_path / "metrics_results.json"
    json_file.write_text(
        '{"run_count": 3, "collision_at_fault": {"mean": 0.02}, '
        '"offroad": 0.0, "dist_to_gt_trajectory": 4.0, '
        '"safety_monitor_triggered": 0.0}',
        encoding="utf-8",
    )
    json_evidence = build_alpasim_evidence(json_file).to_dict()
    assert json_evidence["run_count"] == 3
    assert json_evidence["gates"]["collision_rate"] is False
    assert json_evidence["gates"]["route_deviation_m"] is False

    csv_file = tmp_path / "metrics_results.csv"
    csv_file.write_text(
        "run_uuid,n_clips,n_rollouts,collision_at_fault,offroad,dist_to_gt_trajectory,safety_monitor_triggered\n"
        "a,2,1,0.0,0.0,1.0,0.0\n"
        "b,2,1,0.0,0.0,2.0,0.0\n",
        encoding="utf-8",
    )
    csv_evidence = build_alpasim_evidence(csv_file).to_dict()
    assert csv_evidence["run_count"] == 4
    assert csv_evidence["metrics"]["dist_to_gt_trajectory"] == 1.5
    assert all(value is True for value in csv_evidence["gates"].values())
