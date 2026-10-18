from __future__ import annotations

from benchstudio.integrations import GymnasiumSimulator


class FakeEnv:
    class Unwrapped:
        dt = 0.2

    unwrapped = Unwrapped()

    def reset(self, *, seed):
        return {"seed": seed}, {"source": "fake"}

    def step(self, action):
        return {"action": action}, 1.0, True, False, {"success": True}

    def close(self):
        self.closed = True


def test_gymnasium_adapter_preserves_termination_success_and_clock():
    simulator = GymnasiumSimulator(env=FakeEnv())
    first = simulator.reset(seed=7)
    assert first.sequence == 0
    assert first.sim_time_s == 0.0
    second = simulator.step([1, 2])
    assert second.sequence == 1
    assert second.sim_time_s == 0.2
    assert simulator.is_done()
    assert simulator.is_success()
