"""Open a saved RoboPAD validation attempt and replay its archived evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .libero import LiberoAdapter, _LiberoRuntime

_FIELDS = ("agentview_image", "robot0_eye_in_hand_image", "robot0_eef_pos",
           "robot0_eef_quat", "robot0_gripper_qpos")


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()


def _file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"missing or out-of-campaign file: {relative}")
    return path


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path.name}")
    return value


def _artifact(root: Path, directory: str, name: str, record: dict[str, Any]) -> Path:
    path = _file(root, f"{directory}/{name}")
    hashes = record.get("artifact_sha256")
    if not isinstance(hashes, dict) or hashes.get(name) != _sha(path):
        raise ValueError(f"artifact hash mismatch: {directory}/{name}")
    return path


@dataclass(frozen=True)
class RoboPADReplay:
    """One completed nominal validation attempt from an extracted campaign."""

    adapter: LiberoAdapter
    episode: str
    bddl_sha256: str
    prepared: Path
    actions: Path
    states: Path
    observations: Path
    outcome: dict[str, Any]

    @classmethod
    def open(cls, campaign: str | Path, *, episode: str | None = None) -> RoboPADReplay:
        root = Path(campaign).resolve()
        manifest_path = _file(root, "manifest.json")
        manifest = _json(manifest_path)
        manifest_sha = _sha(manifest_path)
        rows = manifest.get("episodes")
        if manifest.get("stage") != "validation_transfer_v1" or not isinstance(rows, list):
            raise ValueError("expected an extracted RoboPAD validation_transfer_v1 campaign")
        if any(not isinstance(row, dict) or row.get("split") != "validation" for row in rows):
            raise ValueError("campaign contains rows outside the validation split")
        if episode is None and len(rows) == 1:
            episode = rows[0].get("key")
        matches = [row for row in rows if row.get("key") == episode]
        if len(matches) != 1 or not isinstance(episode, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]+", episode
        ):
            keys = ", ".join(str(row.get("key")) for row in rows[:20])
            raise ValueError(f"select one archived episode by key. Available: {keys}")
        row = matches[0]
        adapter = LiberoAdapter(
            row["suite"], task_id=row["task"], initial_state_id=row["initial_state"],
            seed=row["seed"], backend="lerobot",
        )
        identity = f"{adapter.suite}/task{adapter.task_id}/initial{adapter.initial_state_id}"
        bucket = int(hashlib.sha256(f"proposal1-v1:{identity}".encode()).hexdigest()[:8], 16) % 10
        if row.get("episode_id") != identity or bucket not in (6, 7):
            raise ValueError("episode identity mismatch or reserved development fixture")
        bddl_sha = row.get("bddl_sha256")
        if not isinstance(bddl_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", bddl_sha):
            raise ValueError("episode is missing its frozen BDDL digest")

        prepared_dir, result_dir = f"prepared/{episode}", f"evaluations/{episode}/base"
        prepared_path = _file(root, f"{prepared_dir}/record.json")
        prepared = _json(prepared_path)
        result = _json(_file(root, f"{result_dir}/record.json"))
        for record, kind in ((prepared, "prepare"), (result, "evaluate")):
            if (
                record.get("status") != "complete" or record.get("kind") != kind
                or record.get("episode_id") != identity
                or record.get("manifest_sha256") != manifest_sha
            ):
                raise ValueError(f"incomplete or foreign {kind} record")
        if result.get("prepared_record_sha256") != _sha(prepared_path):
            raise ValueError("evaluation does not reference this prepared record")
        outcome = (result.get("branches") or {}).get("nominal")
        if (
            not isinstance(outcome, dict) or outcome.get("status") != "complete"
            or type(outcome.get("success")) is not bool
            or outcome.get("termination") not in ("success", "terminal", "horizon")
        ):
            raise ValueError("the nominal base attempt has no complete outcome to replay")
        return cls(
            adapter, episode, bddl_sha,
            _artifact(root, prepared_dir, "shared.npz", prepared),
            _artifact(root, result_dir, "nominal_actions.npy", result),
            _artifact(root, result_dir, "nominal_states.npy", result),
            _artifact(root, result_dir, "nominal_observations.json", result),
            outcome,
        )

    def _runtime(self, *, action_dtype: str | None = None) -> _LiberoRuntime:
        try:
            from libero.libero import benchmark
            from lerobot.envs.libero import LiberoEnv
        except ImportError as exc:
            raise ValueError(
                f"pinned RoboPAD LeRobot/LIBERO runtime is missing or incompatible: {exc}"
            ) from exc
        if not callable(LiberoEnv):
            raise ValueError("the installed LeRobot does not expose the RoboPAD LiberoEnv")
        gl, platform = os.getenv("MUJOCO_GL"), os.getenv("PYOPENGL_PLATFORM")
        if gl in ("egl", "osmesa") and platform and platform != gl:
            raise ValueError("MUJOCO_GL and PYOPENGL_PLATFORM disagree; use the archived renderer")
        suites = benchmark.get_benchmark_dict()
        if self.adapter.suite not in suites:
            raise ValueError(f"LIBERO assets do not provide suite {self.adapter.suite}")
        suite = suites[self.adapter.suite]()
        if self.adapter.task_id >= len(suite.tasks):
            raise ValueError(f"LIBERO assets do not provide task {self.adapter.task_id}")
        path = Path(suite.get_task_bddl_file_path(self.adapter.task_id))
        if not path.is_file() or _sha(path) != self.bddl_sha256:
            raise ValueError("LIBERO task asset differs from the archived BDDL definition")
        return _LiberoRuntime(self.adapter, action_dtype=action_dtype)

    def check(self) -> dict[str, Any]:
        """Check inputs and render the selected reset state before replay."""
        self._inputs()
        runtime = self._runtime()
        try:
            runtime.restore()
        except Exception as exc:
            raise ValueError(f"LIBERO reset/render failed in this environment: {exc}") from exc
        finally:
            runtime.close()
        return {
            "episode": self.episode,
            "ready": True,
            "checks": ["archive_identity", "artifact_hashes", "bddl", "native_reset"],
            "requested_renderer": os.getenv("MUJOCO_GL"),
            "loaded_modules": {
                name: {
                    "version": str(getattr(sys.modules[name], "__version__", "unknown")),
                    "path": getattr(sys.modules[name], "__file__", None),
                }
                for name in ("lerobot", "libero", "mujoco", "robosuite", "numpy")
                if name in sys.modules
            },
        }

    def _inputs(self) -> tuple[Any, Any, Any, Any, list[dict[str, Any]]]:
        try:
            import numpy as np
        except ImportError as exc:
            raise ValueError("NumPy is required in the pinned RoboPAD environment") from exc
        with np.load(self.prepared, allow_pickle=False) as shared:
            prefix, boundary = shared["prefix"], shared["boundary_state"]
        actions = np.load(self.actions, allow_pickle=False)
        states = np.load(self.states, allow_pickle=False)
        observations = json.loads(self.observations.read_text(encoding="utf-8"))
        count = actions.shape[0] if actions.ndim else 0
        if (
            type(self.outcome.get("steps")) is not int or self.outcome["steps"] != count
            or count == 0 or len(states) != count + 1
            or not isinstance(observations, list) or len(observations) != count + 1
            or any(not isinstance(row, dict) or not set(_FIELDS).issubset(row)
                   for row in observations)
        ):
            raise ValueError("archived actions, states, observations and outcome disagree on coverage")
        if (
            actions.ndim != 2 or prefix.ndim != 2 or states.ndim != 2 or boundary.ndim != 1
            or prefix.shape[1] != actions.shape[1] or states.shape[1:] != boundary.shape
            or any(data.dtype.kind != "f" or not np.isfinite(data).all()
                   for data in (prefix, boundary, actions, states))
        ):
            raise ValueError("archived action/state arrays are incompatible or contain non-finite values")
        return prefix, boundary, actions, states, observations

    def replay(self) -> dict[str, Any]:
        """Replay the archived prefix and nominal actions, with no policy queries."""
        prefix, boundary, actions, states, observations = self._inputs()
        import numpy as np

        count = len(actions)
        runtime = self._runtime()
        differences: list[dict[str, Any]] = []

        def compare_state(actual, expected, step, phase):
            if actual.shape != expected.shape:
                differences.append({"phase": phase, "step": step, "reason": "state_shape"})
                return
            error = float(np.max(np.abs(actual - expected)))
            if not np.isfinite(error) or error > 1e-8:
                differences.append({
                    "phase": phase, "step": step, "reason": "state",
                    "max_abs_error": error if np.isfinite(error) else None,
                })

        def state():
            return runtime.env.env.sim.get_state().flatten()

        try:
            frame = runtime.restore()
            for tick, action in enumerate(prefix, start=1):
                frame = runtime.step(action)
                if frame["stop_reason"] is not None:
                    differences.append({"phase": "prefix", "step": tick, "reason": "terminal"})
                    break
            if not differences:
                # RoboPAD refreshes observations at the branch boundary after prefix replay.
                base = runtime.env.env
                base.sim.forward()
                raw = base._get_observations(force_update=True)
                compare_state(state(), boundary, 0, "boundary")
                for tick, expected in enumerate(observations):
                    compare_state(state(), states[tick], tick, "nominal")
                    fields = [
                        field for field in _FIELDS if field not in raw
                        or hashlib.sha256(np.ascontiguousarray(raw[field]).tobytes()).hexdigest()
                        != expected[field]
                    ]
                    if fields:
                        differences.append({
                            "phase": "nominal", "step": tick, "observation_fields": fields,
                        })
                    if tick == count:
                        reason = ("success" if frame["native_success"] else
                                  "terminal" if frame["stop_reason"] is not None else "horizon")
                        if reason != self.outcome["termination"] or (
                            frame["native_success"] != self.outcome["success"]
                        ):
                            differences.append({
                                "phase": "nominal", "step": tick, "reason": "outcome",
                            })
                        break
                    if frame["stop_reason"] is not None:
                        differences.append({
                            "phase": "nominal", "step": tick, "reason": "early_termination",
                        })
                        break
                    frame = runtime.step(actions[tick])
                    raw = runtime.raw_observation
        finally:
            runtime.close()
        return {
            "episode": self.episode,
            "passed": not differences,
            "first_difference": differences[0] if differences else None,
            "differences": differences,
            "observation_comparison": "exact_archive_hashes",
            "state_atol": 1e-8,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a saved RoboPAD validation attempt.")
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--episode", help="Archive key, required for multi-episode campaigns.")
    parser.add_argument("--check", action="store_true", help="Check the archive and native reset.")
    args = parser.parse_args()
    from .pipeline import ReplayPipeline

    try:
        pipeline = ReplayPipeline.from_archive(args.campaign, episode=args.episode)
        if args.check:
            report = pipeline.check()
        else:
            result = pipeline.run()
            report = {**result.report, "environment": result.environment}
    except (OSError, AttributeError, KeyError, TypeError, RuntimeError, ValueError, ImportError) as exc:
        parser.exit(2, f"BenchStudio replay: {exc}\n")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report.get("passed", report.get("ready")) else 1
