"""Public LIBERO replay API with lazy imports from the user's native environment."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from numbers import Real
from pathlib import Path
from typing import Any, Literal

from .integrations.native_evaluator_evidence import native_frame_signature, replay_native_fixture

_SCHEMA = "benchstudio.libero_replay.v1"
_ACTION_DTYPES = {f"{order}f{size}" for order in ("<", ">") for size in (2, 4, 8)}


def _json_value(value: Any) -> Any:
    if hasattr(value, "shape") and hasattr(value, "dtype") and hasattr(value, "tobytes"):
        if getattr(value.dtype, "hasobject", False):
            raise ValueError("LIBERO replay cannot fingerprint arrays containing objects")
        return {
            "dtype": str(value.dtype),
            "shape": list(value.shape),
            "bytes_sha256": hashlib.sha256(value.tobytes(order="C")).hexdigest(),
        }
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _actions(values: Sequence[Sequence[float]]) -> list[list[float]]:
    actions = []
    for action in values:
        vector = list(action)
        if not vector or any(
            isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
            for value in vector
        ):
            raise ValueError("LIBERO replay requires finite numeric action vectors")
        actions.append([float(value) for value in vector])
    return actions


def _observation_frame(env: Any, raw: Mapping[str, Any], stop: str | None) -> dict[str, Any]:
    success = bool(env.check_success())
    return {
        "state": {"simulator": _json_value(env.env.sim.get_state().flatten())},
        "observation": _json_value(raw),
        "native_success": success,
        "stop_reason": ("goal" if stop == "other" and success else stop),
        # The task evaluator owns episode outcomes. This is simulator replay evidence.
        "recorded_success": None,
    }


@dataclass(frozen=True)
class LiberoAdapter:
    """Select a task and initial-state slot on a pinned LIBERO installation.

    The `native` path follows the OpenPI simulator reset sequence. The
    `lerobot` path follows RoboPAD's LiberoEnv reset and raw simulator step.
    Instantiate this in the environment that already owns the relevant assets
    and renderer. No policy or checkpoint is loaded.
    """

    suite: str
    task_id: int
    initial_state_id: int = 0
    seed: int = 0
    backend: Literal["native", "lerobot"] = "native"
    image_size: int = 256

    def __post_init__(self) -> None:
        if not isinstance(self.suite, str) or not self.suite.strip():
            raise ValueError("LIBERO suite must be a nonempty string")
        if self.backend not in ("native", "lerobot"):
            raise ValueError("LIBERO backend must be native or lerobot")
        for name in ("task_id", "initial_state_id", "seed", "image_size"):
            value = getattr(self, name)
            if type(value) is not int or value < (1 if name == "image_size" else 0):
                raise ValueError(f"invalid LIBERO {name}")

    def capture(self, actions: Sequence[Sequence[float]]) -> dict[str, Any]:
        """Capture a serializable reference for a fixed action sequence."""
        dtype = getattr(getattr(actions, "dtype", None), "str", None)
        dtype = self._action_dtype(dtype if self.backend == "lerobot" else None)
        actions = _actions(actions)
        runtime = _LiberoRuntime(self, action_dtype=dtype)
        try:
            frame = runtime.restore()
            frames = [native_frame_signature(frame)]
            for action in actions:
                if frame["stop_reason"] is not None:
                    raise ValueError("saved actions continue after LIBERO termination")
                frame = runtime.step(action)
                frames.append(native_frame_signature(frame))
        finally:
            runtime.close()
        return {
            "schema": _SCHEMA,
            "task": asdict(self),
            "actions": actions,
            "action_dtype": dtype,
            "frames": frames,
        }

    def _action_dtype(self, dtype: Any) -> str | None:
        if dtype is None:
            return None
        if self.backend != "lerobot" or not isinstance(dtype, str) or dtype not in _ACTION_DTYPES:
            raise ValueError("invalid LIBERO replay action dtype")
        return dtype

    def replay(self, reference: Mapping[str, Any]) -> dict[str, Any]:
        """Restore in a fresh environment and report the first divergence."""
        if reference.get("schema") != _SCHEMA or reference.get("task") != asdict(self):
            raise ValueError("replay reference does not match the selected LIBERO task and backend")
        if not isinstance(reference.get("actions"), list) or not isinstance(
            reference.get("frames"), list
        ):
            raise ValueError("LIBERO replay reference requires action and frame lists")
        actions = _actions(reference["actions"])
        dtype = self._action_dtype(reference.get("action_dtype"))
        runtime = _LiberoRuntime(self, action_dtype=dtype)
        try:
            report = replay_native_fixture(
                fixture={},
                actions=actions,
                expected=reference["frames"],
                restore=runtime.restore,
                step=runtime.step,
            )
        finally:
            runtime.close()
        # A simulator replay has no independent task evaluator outcome.
        report.pop("qualification_fixture")
        return report


def replay_libero(reference: Mapping[str, Any]) -> dict[str, Any]:
    """Replay a saved LIBERO reference without reconstructing adapter options."""
    task = reference.get("task")
    if not isinstance(task, dict):
        raise ValueError("LIBERO replay reference requires task metadata")
    return LiberoAdapter(**task).replay(reference)


class _LiberoRuntime:
    def __init__(self, config: LiberoAdapter, *, action_dtype: str | None) -> None:
        self.config = config
        self.action_dtype = action_dtype
        self.owner: Any = None
        self.env: Any = None

    def restore(self) -> dict[str, Any]:
        cfg = self.config
        try:
            from libero.libero import benchmark, get_libero_path
        except ImportError as exc:
            raise ImportError("run LIBERO replay in your pinned LIBERO environment") from exc
        suites = benchmark.get_benchmark_dict()
        if cfg.suite not in suites:
            raise ValueError(f"unknown LIBERO suite: {cfg.suite}")
        suite = suites[cfg.suite]()
        if cfg.task_id >= len(suite.tasks):
            raise ValueError(f"unknown LIBERO task: {cfg.task_id}")
        states = suite.get_task_init_states(cfg.task_id)
        if cfg.initial_state_id >= len(states):
            raise ValueError(f"unknown LIBERO initial-state slot: {cfg.initial_state_id}")
        if cfg.backend == "lerobot":
            try:
                from lerobot.envs.libero import LiberoEnv
            except ImportError as exc:
                raise ImportError("the RoboPAD replay path requires its pinned LeRobot runtime") from exc
            self.owner = LiberoEnv(
                suite, cfg.task_id, cfg.suite, obs_type="pixels_agent_pos",
                episode_index=cfg.initial_state_id,
                observation_height=cfg.image_size, observation_width=cfg.image_size,
            )
            self.owner.init_state_id = cfg.initial_state_id
            self.owner.reset(seed=cfg.seed)
            self.env = self.owner._env
            base = self.env.env
            base.sim.forward()
            raw = base._get_observations(force_update=True)
        else:
            from libero.libero.envs import OffScreenRenderEnv

            task = suite.get_task(cfg.task_id)
            bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
            self.owner = self.env = OffScreenRenderEnv(
                bddl_file_name=str(bddl),
                camera_heights=cfg.image_size,
                camera_widths=cfg.image_size,
            )
            self.env.seed(cfg.seed)
            self.env.reset()
            raw = self.env.set_init_state(states[cfg.initial_state_id])
        return _observation_frame(self.env, raw, None)

    def step(self, action: Sequence[float]) -> dict[str, Any]:
        if self.config.backend == "lerobot":
            import numpy as np

            action = np.asarray(action, dtype=self.action_dtype)
        result = self.env.step(action)
        if len(result) == 4:
            raw, _, done, info = result
            truncated = bool(info.get("TimeLimit.truncated", False)) if done else False
        elif len(result) == 5:
            raw, _, done, truncated, _ = result
        else:
            raise ValueError("unexpected LIBERO step response")
        stop = "horizon" if truncated else "other" if done else None
        frame = _observation_frame(self.env, raw, stop)
        if self.config.backend == "lerobot" and stop is None and frame["native_success"]:
            frame["stop_reason"] = "goal"
        return frame

    def close(self) -> None:
        if self.owner is not None:
            self.owner.close()
