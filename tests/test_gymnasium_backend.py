from __future__ import annotations

import pytest

pytest.importorskip("gymnasium")

from benchstudio.contracts import ActionChunk  # noqa: E402
from benchstudio.integrations import GymnasiumSimulator  # noqa: E402
from benchstudio.runner import RunConfig, run_episodes  # noqa: E402


class _CartPolePolicy:
    policy_id = "cartpole_zero_policy"

    def reset(self, *, seed: int) -> None:
        self.seed = seed

    def predict(self, observation, *, denoising_steps):
        del observation, denoising_steps
        return ActionChunk((0,))


def test_gymnasium_adapter_runs_a_closed_loop_episode(tmp_path):
    simulator = GymnasiumSimulator(
        "CartPole-v1",
        dt_s=0.02,
        stop_on_success=True,
        success_fn=lambda _observation, reward, _terminated, _truncated, _info: reward > 0,
    )
    summary = run_episodes(
        _CartPolePolicy(),
        simulator,
        RunConfig(episodes=1, action_prefix=1, max_episode_steps=3),
        tmp_path / "run",
    )
    assert summary["scheduled_episode_count"] == 1
    assert summary["completed_episode_count"] == 1
    assert summary["success_count"] == 1
    assert summary["episodes"][0]["steps"] == 1
