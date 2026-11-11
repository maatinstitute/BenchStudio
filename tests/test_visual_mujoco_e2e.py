"""Real MuJoCo camera -> mmap policy -> BenchStudio episode, when GL is present.

This uses a diagnostic external policy, NOT a trained checkpoint or VLA score.
"""
from __future__ import annotations

import json
import sys

import pytest

mujoco = pytest.importorskip("mujoco")
np = pytest.importorskip("numpy")

from benchstudio.external_policy import PersistentExternalCommandPolicy
from benchstudio.integrations.mujoco import MujocoSimulator
from benchstudio.runner import RunConfig, run_episodes


_POLICY = '''import json, os, sys
from benchstudio.local_tensors import open_local_tensors
for line in sys.stdin:
    message = json.loads(line)
    operation = message["operation"]
    if operation == "reset":
        response = {"status": "reset"}
    elif operation == "predict":
        with open_local_tensors(message["observation"]["payload"], root=os.environ["BENCHSTUDIO_LOCAL_TENSOR_ROOT"]) as payload:
            image = payload["policy_batch"]["front"]
            response = {
                "actions": [[0.0]],
                "metadata": {"image_shape": list(image.shape), "image_dtype": str(image.dtype)},
            }
    elif operation == "close":
        response = {"status": "closed"}
    else:
        raise ValueError("unexpected operation")
    print(json.dumps(response), flush=True)
    if operation == "close":
        break
'''


def test_real_physics_visual_policy_bridge(tmp_path):
    xml = tmp_path / "slider.xml"
    xml.write_text('''<mujoco><option timestep="0.01"/><worldbody>
      <camera name="front" pos="0 -2 1" xyaxes="1 0 0 0 0 1"/>
      <body pos="0 0 0"><joint name="slide" type="slide" axis="1 0 0"/>
        <geom type="box" size="0.1 0.1 0.1" mass="1"/></body>
      </worldbody><actuator><motor joint="slide" gear="1"/></actuator></mujoco>''')
    try:
        simulator = MujocoSimulator(
            xml, max_steps=2, camera_name="front",
            camera_width=48, camera_height=32,
            success_fn=lambda _model, data: data.time + 1e-12 >= 0.02,
            observation_fn=lambda payload: {
                "policy_batch": {"front": payload["images"]["front"]},
                "qpos": payload["qpos"],
            },
        )
    except (RuntimeError, ImportError) as exc:
        pytest.skip(f"MuJoCo renderer unavailable: {exc}")
    policy = PersistentExternalCommandPolicy(
        [sys.executable, "-c", _POLICY], tensor_transport="mmap", device="cpu",
        timeout_s=10,
    )
    result = run_episodes(
        policy, simulator,
        RunConfig(episodes=1, action_prefix=1, max_episode_steps=2),
        tmp_path / "visual-run",
    )
    assert result["campaign_status"] == "completed"
    assert result["success_count"] == 1
    assert result["episodes"][0]["steps"] == 2
    records = [
        json.loads(line)
        for line in (tmp_path / "visual-run" / "episodes.jsonl").read_text().splitlines()
    ]
    actions = [event for event in records if event["event_type"] == "action_executed"]
    assert len(actions) == 2
    assert all(
        event["policy_metadata"] == {"image_shape": [32, 48, 3], "image_dtype": "uint8"}
        for event in actions
    )
