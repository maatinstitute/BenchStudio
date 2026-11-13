from __future__ import annotations

import pytest

from reva.adapters import default_registry
from reva.contracts import ActionChunk
from reva.runner import RunConfig, run_episodes


class _ZeroMuJoCoPolicy:
    policy_id = "registry_zero_mujoco_policy"

    def reset(self, *, seed: int) -> None:
        self.seed = seed

    def predict(self, observation, *, denoising_steps):
        del observation, denoising_steps
        return ActionChunk(((0.0,),))


def test_registry_instantiates_real_mujoco_backend(tmp_path):
    pytest.importorskip("mujoco")
    xml = tmp_path / "minimal.xml"
    xml.write_text(
        """
        <mujoco>
          <option timestep="0.01"/>
          <worldbody>
            <body name="slider" pos="0 0 0">
              <joint name="slide" type="slide" axis="1 0 0"/>
              <geom type="box" size="0.1 0.1 0.1" mass="1"/>
            </body>
          </worldbody>
          <actuator><motor joint="slide" gear="1"/></actuator>
        </mujoco>
        """,
        encoding="utf-8",
    )
    simulator = default_registry(discover_external=False).create(
        "mujoco",
        xml_path=xml,
        max_steps=2,
        success_fn=lambda _model, data: data.time >= 0.02,
    )
    summary = run_episodes(
        _ZeroMuJoCoPolicy(),
        simulator,
        RunConfig(episodes=1, action_prefix=1, max_episode_steps=2),
        tmp_path / "run",
    )
    assert summary["success_count"] == 1


def test_registry_instantiates_real_gymnasium_backend(tmp_path):
    pytest.importorskip("gymnasium")
    simulator = default_registry(discover_external=False).create(
        "gymnasium",
        env_id="CartPole-v1",
        dt_s=0.02,
        stop_on_success=True,
        success_fn=lambda _observation, reward, _terminated, _truncated, _info: reward > 0,
    )

    class _ZeroCartPolePolicy:
        policy_id = "registry_zero_cartpole_policy"

        def reset(self, *, seed: int) -> None:
            self.seed = seed

        def predict(self, observation, *, denoising_steps):
            del observation, denoising_steps
            return ActionChunk((0,))

    summary = run_episodes(
        _ZeroCartPolePolicy(),
        simulator,
        RunConfig(episodes=1, action_prefix=1, max_episode_steps=3),
        tmp_path / "run",
    )
    assert summary["success_count"] == 1
