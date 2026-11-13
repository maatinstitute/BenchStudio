from __future__ import annotations

from reva.replay import ReplayPolicy, ReplaySimulator, load_joint_sequence
from reva.runner import RunConfig, run_episodes


def test_replay_trace_can_drive_reva(tmp_path):
    trace = tmp_path / "trace.ndjson"
    trace.write_text(
        '{"stream":"robot_joints","state":{"joint_positions":{"j1":0.1}}}\n'
        '{"stream":"robot_joints","state":{"joint_positions":{"j1":0.2}}}\n'
    )
    assert load_joint_sequence(trace) == [{"j1": 0.1}, {"j1": 0.2}]
    summary = run_episodes(
        ReplayPolicy.from_trace(trace),
        ReplaySimulator(steps=2),
        RunConfig(episodes=1, action_prefix=1),
        tmp_path / "run",
    )
    assert summary["scheduled_success_rate"] == 1.0
