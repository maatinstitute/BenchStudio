from __future__ import annotations

import pytest

from benchstudio.integrations.genesis import GenesisSimulator


class _FakeScene:
    def __init__(self):
        self.value = 0
        self.closed = False

    def reset(self, *, seed: int):
        self.value = seed

    def step(self):
        self.value += 1

    def destroy(self):
        self.closed = True


def test_genesis_adapter_binds_explicit_scene_callbacks():
    scene = _FakeScene()
    simulator = GenesisSimulator(
        scene,
        observation_fn=lambda current: {"value": current.value},
        action_fn=lambda current, action: setattr(current, "value", current.value + action),
        success_fn=lambda current: current.value >= 5,
        dt_s=0.02,
        max_steps=10,
    )
    first = simulator.reset(seed=2)
    assert first.payload == {"value": 2}
    next_observation = simulator.step(3)
    assert next_observation.sequence == 1
    assert next_observation.payload == {"value": 6}
    assert simulator.is_done() is True
    assert simulator.is_success() is True
    simulator.close()
    assert scene.closed is True


@pytest.mark.parametrize("dt_s", [True, "0.01", float("nan")])
def test_genesis_rejects_coerced_timing_controls(dt_s):
    scene = _FakeScene()
    with pytest.raises(ValueError, match="dt_s"):
        GenesisSimulator(
            scene,
            observation_fn=lambda current: {"value": current.value},
            action_fn=lambda current, action: None,
            dt_s=dt_s,
        )
