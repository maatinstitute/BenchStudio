import numpy as np
import pytest

from ival.integrations.robopad_rollout import RolloutFailure, rollout


class _World:
    def __init__(self, success_at=None, done_at=None):
        self.actions = []
        self.success_at = success_at
        self.done_at = done_at

    def step(self, action):
        self.actions.append(action.copy())
        return len(self.actions), 0.0, len(self.actions) == self.done_at, {}

    def sample(self, observation):
        return {
            "native_success": observation == self.success_at,
            "native_success_available": True,
            "step": observation,
        }


def test_committed_prefix_and_absolute_suffix_cadence():
    prefix = np.arange(35, dtype=float).reshape(5, 7)
    world = _World()
    calls = []

    def predict(observation, step):
        calls.append((observation, step))
        return np.full((10, 7), -step, dtype=float)

    result = rollout(world, 0, prefix, predict, world.sample, horizon=27)
    np.testing.assert_array_equal(result["actions"][:5], prefix)
    assert calls == [(5, 5), (15, 15), (25, 25)]
    assert result["termination"] == "horizon"
    assert result["completed_steps"] == 27


def test_prediction_and_step_errors_retain_explicit_partial_state():
    world = _World()
    with pytest.raises(RolloutFailure) as caught:
        rollout(
            world,
            0,
            np.ones((5, 7)),
            lambda *_: (_ for _ in ()).throw(RuntimeError("inference failed")),
            world.sample,
            horizon=200,
        )
    assert caught.value.partial["completed_steps"] == 5
    assert caught.value.partial["failure_stage"] == "prediction"
    world.step = lambda action: (_ for _ in ()).throw(RuntimeError("simulator failed"))
    with pytest.raises(RolloutFailure) as caught:
        rollout(world, 0, np.ones((5, 7)), None, world.sample, horizon=200)
    assert caught.value.partial["completed_steps"] == 0
    np.testing.assert_array_equal(caught.value.partial["pending_action"], np.ones(7))
    assert caught.value.partial["failure_stage"] == "environment_step"


def test_success_stop_and_terminal_statuses_are_distinct():
    world = _World(success_at=2)
    result = rollout(
        world,
        0,
        np.ones((5, 7)),
        lambda *_: pytest.fail("suffix queried"),
        world.sample,
        horizon=200,
    )
    assert result["termination"] == "native_success"
    assert result["completed_steps"] == 2
    world = _World()
    result = rollout(
        world,
        0,
        np.ones((5, 7)),
        None,
        world.sample,
        horizon=200,
        should_stop=lambda: len(world.actions) == 3,
    )
    assert result["termination"] == "wall_clock_limit"
    assert result["completed_steps"] == 3
    world = _World(done_at=1)
    result = rollout(world, 0, np.ones((5, 7)), None, world.sample, horizon=200)
    assert result["termination"] == "environment_terminal"
    assert result["completed_steps"] == 1


def test_missing_signal_and_invalid_actions_fail_before_execution():
    world = _World()
    with pytest.raises(ValueError):
        rollout(world, 0, np.ones((1, 7)), None, lambda _: {"native_success": False}, horizon=200)
    assert world.actions == []
    with pytest.raises(ValueError):
        rollout(world, 0, np.full((1, 7), np.nan), None, world.sample, horizon=200)
    assert world.actions == []
