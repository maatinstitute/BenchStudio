"""Optional MuJoCo simulator adapter.

The dependency is imported only when an adapter instance is created. BenchStudio
owns the temporal/evidence boundary here; task scoring and model-specific
success criteria remain supplied by the caller.
"""

from __future__ import annotations

import importlib
import math
import time
from collections.abc import Mapping
from numbers import Real
from pathlib import Path
from typing import Any, Callable, Iterable

from ..contracts import Observation, Timestamp

SuccessFn = Callable[[Any, Any], bool]


class MujocoSimulator:
    simulator_id = "mujoco_simulator"

    def __init__(
        self,
        xml_path: str | Path,
        *,
        max_steps: int = 1000,
        frame_skip: int = 1,
        success_fn: SuccessFn | None = None,
        initial_qpos: Iterable[float] | None = None,
        camera_name: str | None = None,
        camera_width: int = 256,
        camera_height: int = 256,
        observation_fn: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
            raise ValueError("max_steps must be positive")
        if isinstance(frame_skip, bool) or not isinstance(frame_skip, int) or frame_skip < 1:
            raise ValueError("frame_skip must be positive")
        if camera_name is not None and (not isinstance(camera_name, str) or not camera_name):
            raise ValueError("camera_name must be a non-empty string or None")
        for name, value in (("camera_width", camera_width), ("camera_height", camera_height)):
            if type(value) is not int or not 1 <= value <= 4096:
                raise ValueError(f"{name} must be an integer between 1 and 4096")
        if observation_fn is not None and not callable(observation_fn):
            raise TypeError("observation_fn must be callable")
        self.xml_path = Path(xml_path)
        if not self.xml_path.is_file():
            raise FileNotFoundError(self.xml_path)
        try:
            mujoco = importlib.import_module("mujoco")
        except ModuleNotFoundError as exc:
            if exc.name == "mujoco":
                raise RuntimeError(
                    "MuJoCo backend requires the optional 'mujoco' dependency"
                ) from exc
            raise
        self._mujoco = mujoco
        self.model = mujoco.MjModel.from_xml_path(str(self.xml_path))
        self.data = mujoco.MjData(self.model)
        self.camera_name = camera_name
        self.observation_fn = observation_fn
        self._renderer = None
        if camera_name is not None:
            if mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name) < 0:
                raise ValueError(f"camera {camera_name!r} is not defined in the MJCF scene")
            # Renderer creation is explicit: no hidden headless or physics fallback.
            self._renderer = mujoco.Renderer(
                self.model, height=camera_height, width=camera_width
            )
        self.max_steps = max_steps
        self.frame_skip = frame_skip
        self.success_fn = success_fn
        self.initial_qpos = tuple(initial_qpos) if initial_qpos is not None else None
        if self.initial_qpos is not None and len(self.initial_qpos) != self.model.nq:
            raise ValueError("initial_qpos length must equal MuJoCo model.nq")
        self._step = 0
        self._success = False

    def reset(self, *, seed: int) -> Observation:
        del seed  # MuJoCo state is deterministic unless the caller randomizes it.
        self._mujoco.mj_resetData(self.model, self.data)
        if self.initial_qpos is not None:
            self.data.qpos[:] = self.initial_qpos
        self._mujoco.mj_forward(self.model, self.data)
        self._step = 0
        self._success = self._evaluate_success()
        return self.observe()

    def observe(self) -> Observation:
        sim_time_s = float(self.data.time)
        payload: dict[str, Any] = {
            "qpos": tuple(float(value) for value in self.data.qpos),
            "qvel": tuple(float(value) for value in self.data.qvel),
            "ctrl": tuple(float(value) for value in self.data.ctrl),
        }
        if self._renderer is not None:
            self._renderer.update_scene(self.data, camera=self.camera_name)
            payload["images"] = {"front": self._renderer.render().copy()}
        if self.observation_fn is not None:
            prepared = self.observation_fn(payload)
            if not isinstance(prepared, Mapping):
                raise ValueError("observation_fn must return an observation mapping")
            payload = dict(prepared)
        return Observation(
            sequence=self._step,
            sim_time_s=sim_time_s,
            payload=payload,
            source_timestamp=Timestamp(round(sim_time_s * 1_000_000_000), "sim_time"),
            received_monotonic_ns=time.monotonic_ns(),
        )

    def step(self, action: Any) -> Observation:
        if self.model.nu == 1 and not isinstance(action, (str, bytes)):
            try:
                values = tuple(action)
            except TypeError:
                values = (action,)
        elif not isinstance(action, (str, bytes)):
            try:
                values = tuple(action)
            except TypeError as exc:
                raise ValueError(f"action must be an iterable of length {self.model.nu}") from exc
        else:
            values = ()
        if len(values) != self.model.nu:
            raise ValueError(f"action length must equal MuJoCo model.nu ({self.model.nu})")
        if any(isinstance(value, bool) or not isinstance(value, Real) for value in values):
            raise ValueError("MuJoCo actions must be numeric")
        numeric = tuple(float(value) for value in values)
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("MuJoCo actions must be finite")
        self.data.ctrl[:] = numeric
        for _ in range(self.frame_skip):
            self._mujoco.mj_step(self.model, self.data)
        self._step += 1
        self._success = self._evaluate_success()
        return self.observe()

    def is_done(self) -> bool:
        return self._step >= self.max_steps or self._success

    def is_success(self) -> bool:
        return self._success

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
        self.data = None
        self.model = None

    def _evaluate_success(self) -> bool:
        return bool(self.success_fn(self.model, self.data)) if self.success_fn else False
