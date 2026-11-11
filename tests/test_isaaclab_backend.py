from __future__ import annotations

import pytest

from benchstudio.integrations import IsaacLabSimulator


class _FakeIsaacEnv:
    step_dt = 0.05

    def __init__(self):
        self.value = 0
        self.closed = False

    def reset(self, *, seed: int):
        self.value = seed
        return {"state": [self.value, 0]}, {"success": [False, False]}

    def step(self, action):
        self.value += action
        return (
            {"state": [self.value, 0]},
            1.0,
            [self.value >= 3, False],
            {"success": [self.value >= 3, False]},
        )

    def close(self):
        self.closed = True


def test_isaaclab_adapter_selects_one_vectorized_environment():
    env = _FakeIsaacEnv()
    simulator = IsaacLabSimulator(env, env_index=0, max_steps=5)
    first = simulator.reset(seed=1)
    assert first.payload == {"state": [1, 0]}
    next_observation = simulator.step(2)
    assert next_observation.sequence == 1
    assert next_observation.sim_time_s == 0.05
    assert simulator.is_done() is True
    assert simulator.is_success() is True
    simulator.close()
    assert env.closed is True


@pytest.mark.parametrize("dt_s", [True, "0.05", float("inf")])
def test_isaaclab_rejects_coerced_timing_controls(dt_s):
    with pytest.raises(ValueError, match="dt_s"):
        IsaacLabSimulator(_FakeIsaacEnv(), dt_s=dt_s)
