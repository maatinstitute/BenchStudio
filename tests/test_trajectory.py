from __future__ import annotations

from benchstudio.trajectory import compare_trajectories


def test_trajectory_comparison_localizes_joint_split(tmp_path):
    first = tmp_path / "a.ndjson"
    second = tmp_path / "b.ndjson"
    first.write_text(
        '{"t_ms":0,"stream":"robot_joints","state":{"joint_positions":{"j1":0.0}}}\n'
        '{"t_ms":100,"stream":"robot_joints","state":{"joint_positions":{"j1":0.0}}}\n'
    )
    second.write_text(
        '{"t_ms":0,"stream":"robot_joints","state":{"joint_positions":{"j1":0.0}}}\n'
        '{"t_ms":100,"stream":"robot_joints","state":{"joint_positions":{"j1":0.2}}}\n'
    )
    report = compare_trajectories(first, second)
    assert report is not None
    assert report["split"]["t_ms"] == 100
    assert report["split"]["metric"] == "joint_rmse_rad"


def test_trajectory_alignment_does_not_reuse_a_frame(tmp_path):
    first = tmp_path / "a.ndjson"
    second = tmp_path / "b.ndjson"
    first.write_text(
        '{"t_ms":0,"stream":"robot_joints","state":{"joint_positions":{"j1":0.0}}}\n'
        '{"t_ms":40,"stream":"robot_joints","state":{"joint_positions":{"j1":0.1}}}\n'
    )
    second.write_text('{"t_ms":0,"stream":"robot_joints","state":{"joint_positions":{"j1":0.0}}}\n')
    report = compare_trajectories(first, second)
    assert report is not None
    assert report["compared_frames"] == 1
