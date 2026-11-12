"""Real MuJoCo RGB observation path, when a renderer is available."""
from __future__ import annotations

import pytest

mujoco = pytest.importorskip("mujoco")
np = pytest.importorskip("numpy")

from benchstudio.integrations.mujoco import MujocoSimulator  # noqa: E402


def test_mujoco_camera_observations_have_rgb_and_state(tmp_path):
    xml = tmp_path / "scene.xml"
    xml.write_text('''<mujoco><option timestep="0.01"/><worldbody>
      <camera name="front" pos="0 -2 1" xyaxes="1 0 0 0 0 1"/>
      <body pos="0 0 0"><joint name="slide" type="slide" axis="1 0 0"/>
        <geom type="box" size="0.1 0.1 0.1" mass="1"/></body>
      </worldbody><actuator><motor joint="slide" gear="1"/></actuator></mujoco>''')
    try:
        sim = MujocoSimulator(
            xml, max_steps=2, camera_name="front",
            camera_width=48, camera_height=32,
        )
    except (RuntimeError, ImportError) as exc:
        pytest.skip(f"MuJoCo camera renderer unavailable on this runner: {exc}")
    try:
        obs = sim.reset(seed=1)
        image = obs.payload["images"]["front"]
        assert image.shape == (32, 48, 3)
        assert image.dtype == np.uint8
        assert "qpos" in obs.payload
        next_obs = sim.step(0)
        assert next_obs.payload["images"]["front"].shape == image.shape
    finally:
        sim.close()


def test_mujoco_rejects_camera_without_matching_scene_camera(tmp_path):
    xml = tmp_path / "scene.xml"
    xml.write_text('<mujoco><worldbody><geom type="sphere" size="0.1"/></worldbody></mujoco>')
    with pytest.raises(ValueError, match="camera"):
        MujocoSimulator(xml, camera_name="front")
