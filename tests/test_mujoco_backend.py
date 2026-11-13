from __future__ import annotations

import pytest

mujoco = pytest.importorskip("mujoco")

from ival.contracts import ActionChunk  # noqa: E402
from ival.integrations import MujocoSimulator  # noqa: E402
from ival.runner import RunConfig, run_episodes  # noqa: E402


class _ZeroPolicy:
    policy_id = "zero_mujoco_policy"

    def reset(self, *, seed: int) -> None:
        self.seed = seed

    def predict(self, observation, *, denoising_steps):
        del observation, denoising_steps
        return ActionChunk(((0.0,),))


def test_mujoco_adapter_runs_a_closed_loop_episode(tmp_path):
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
    simulator = MujocoSimulator(
        xml,
        max_steps=2,
        success_fn=lambda _model, data: data.time >= 0.02,
    )
    summary = run_episodes(
        _ZeroPolicy(),
        simulator,
        RunConfig(episodes=1, action_prefix=1, max_episode_steps=2),
        tmp_path / "run",
    )
    assert summary["scheduled_episode_count"] == 1
    assert summary["completed_episode_count"] == 1
    assert summary["success_count"] == 1


def test_mujoco_single_actuator_accepts_scalar_action(tmp_path):
    xml = tmp_path / "scalar.xml"
    xml.write_text(
        """
        <mujoco>
          <worldbody>
            <body>
              <joint name="slide" type="slide" axis="1 0 0"/>
              <geom type="box" size="0.1 0.1 0.1" mass="1"/>
            </body>
          </worldbody>
          <actuator><motor joint="slide" gear="1"/></actuator>
        </mujoco>
        """,
        encoding="utf-8",
    )
    simulator = MujocoSimulator(xml, max_steps=1)
    simulator.reset(seed=1)
    observation = simulator.step(0.0)
    assert observation.sequence == 1
    simulator.close()


@pytest.mark.parametrize("field", ["max_steps", "frame_skip"])
def test_mujoco_rejects_boolean_step_controls(tmp_path, field):
    kwargs = {field: True}
    with pytest.raises(ValueError, match="positive"):
        MujocoSimulator(tmp_path / "missing.xml", **kwargs)
