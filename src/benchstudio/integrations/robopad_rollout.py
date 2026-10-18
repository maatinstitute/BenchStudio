"""RoboPAD committed-prefix rollout and explicit partial-failure semantics."""

from __future__ import annotations

from typing import Any, Callable


class RolloutFailure(RuntimeError):
    """Execution stopped with retained partial trace and an explicit stage."""

    def __init__(self, error: BaseException, partial: dict[str, Any]):
        super().__init__(f"{type(error).__name__}: {error}")
        self.partial = partial


def _actions(value: Any, minimum: int):
    import numpy as np

    value = np.asarray(value)
    if (
        value.ndim != 2
        or value.shape[1] != 7
        or len(value) < minimum
        or not np.isfinite(value).all()
    ):
        raise ValueError("finite action matrix with seven columns required")
    return value.copy()


def _sample(sample: Callable[[Any], dict[str, Any]], observation: Any) -> dict[str, Any]:
    result = sample(observation)
    if not bool(result.get("native_success_available", False)) or "native_success" not in result:
        raise ValueError("native task-success signal must be available")
    return result


def rollout(
    env: Any,
    obs: Any,
    prefix: Any,
    predict: Callable[[Any, int], Any] | None,
    sample: Callable[[Any], dict[str, Any]],
    *,
    horizon: int = 200,
    should_stop: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    """Execute a committed prefix, then query a suffix every 10 actions."""
    import numpy as np

    prefix = _actions(prefix, 1)
    if type(horizon) is not int or horizon < len(prefix):
        raise ValueError("integer horizon must include the committed prefix")
    prefix_length = len(prefix)
    chunk = prefix
    samples = [_sample(sample, obs)]
    actions: list[Any] = []
    rewards: list[float] = []
    dones: list[bool] = []
    termination = "horizon"
    pending_action = None
    failure_stage = "before_action"

    def result() -> dict[str, Any]:
        return {
            "actions": np.asarray(actions).reshape(-1, 7),
            "reward": np.asarray(rewards),
            "done": np.asarray(dones),
            "samples": samples,
            "completed_steps": len(actions),
            "termination": termination,
        }

    try:
        for step in range(horizon):
            if bool(samples[-1]["native_success"]):
                termination = "native_success"
                break
            if should_stop():
                termination = "wall_clock_limit"
                break
            failure_stage = "prediction"
            if step >= prefix_length and (step - prefix_length) % 10 == 0:
                if predict is None:
                    raise ValueError("suffix predictor required")
                chunk = _actions(predict(obs, step), min(10, horizon - step))
            offset = step if step < prefix_length else (step - prefix_length) % 10
            action = chunk[offset].copy()
            pending_action = action.copy()
            failure_stage = "environment_step"
            obs, reward, done, _ = env.step(action)
            actions.append(action)
            pending_action = None
            rewards.append(float(reward))
            dones.append(bool(done))
            failure_stage = "post_action_sample"
            samples.append(_sample(sample, obs))
            if bool(samples[-1]["native_success"]):
                termination = "native_success"
                break
            if done:
                termination = "environment_terminal"
                break
    except BaseException as error:
        termination = "exception"
        partial = {**result(), "failure_stage": failure_stage, "pending_action": pending_action}
        raise RolloutFailure(error, partial) from error
    return result()
