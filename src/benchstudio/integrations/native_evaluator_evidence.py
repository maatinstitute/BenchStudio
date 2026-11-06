"""Runtime identity and policy-free replay for a native evaluator process."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

_FILE_GROUPS = {"runner", "checkpoint", "assets", "normalization"}
_GL_FIELDS = ("vendor", "renderer", "version")


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def active_opengl_identity() -> dict[str, str]:
    """Read the renderer from the native evaluator's current OpenGL context."""
    from OpenGL import GL

    values = {
        name: GL.glGetString(token)
        for name, token in zip(_GL_FIELDS, (GL.GL_VENDOR, GL.GL_RENDERER, GL.GL_VERSION))
    }
    if any(not isinstance(value, bytes) or not value.strip() for value in values.values()):
        raise ValueError("no active OpenGL context or incomplete renderer identity")
    return {name: value.decode("utf-8") for name, value in values.items()}


def capture_native_runtime(
    *,
    modules: Mapping[str, ModuleType],
    files: Mapping[str, Mapping[str, Path]],
    read_renderer: Callable[[], Mapping[str, str]] = active_opengl_identity,
) -> dict[str, Any]:
    """Fingerprint imported modules and the actual files selected by the launcher.

    Module keys are distribution names. File group entries use stable logical
    names and point to resolved inputs, including every relevant asset file.
    Invoke inside the evaluator process after imports and renderer setup.
    """
    if not modules or set(files) != _FILE_GROUPS or any(not group for group in files.values()):
        raise ValueError("runtime capture requires imported modules and every file group")
    renderer = dict(read_renderer())
    if any(
        not isinstance(renderer.get(key), str) or not renderer[key].strip()
        for key in _GL_FIELDS
    ):
        raise ValueError("runtime capture requires an active renderer identity")

    loaded = {}
    module_paths = {}
    for distribution, module in sorted(modules.items()):
        source = getattr(module, "__file__", None)
        if not isinstance(source, str):
            raise ValueError(f"imported module {distribution} has no source path")
        path = Path(source).resolve(strict=True)
        version = getattr(module, "__version__", None)
        loaded[distribution] = {
            "module": module.__name__,
            "imported_version": str(version) if version is not None else None,
            "installed_version": importlib.metadata.version(distribution),
            "imported_file_sha256": _file_digest(path),
        }
        module_paths[distribution] = str(path)
    stack = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "kernel_release": platform.release(),
        "architecture": platform.machine(),
        "modules": loaded,
    }
    file_hashes = {}
    file_paths = {}
    for group, entries in sorted(files.items()):
        file_hashes[group] = {}
        file_paths[group] = {}
        for name, source in sorted(entries.items()):
            path = source.resolve(strict=True)
            file_hashes[group][name] = _file_digest(path)
            file_paths[group][name] = str(path)
    return {
        "schema": "benchstudio.native_runtime_capture.v1",
        "identity": {
            "simulator_stack": _digest(stack),
            "renderer": _digest(renderer),
            **{group: _digest(hashes) for group, hashes in file_hashes.items()},
        },
        "stack": stack,
        "renderer": renderer,
        "files": file_hashes,
        "python_executable": str(Path(sys.executable).resolve()),
        "resolved_module_paths": module_paths,
        "resolved_file_paths": file_paths,
    }


def native_frame_signature(frame: Mapping[str, Any]) -> dict[str, Any]:
    """Fingerprint a saved frame using the same representation as the replay."""
    state, observation = frame["state"], frame["observation"]
    if not isinstance(state, dict) or not state:
        raise ValueError("native frame requires a nonempty state snapshot")
    if not isinstance(observation, dict) or not observation:
        raise ValueError("native frame requires named observation fields")
    native = frame["native_success"]
    recorded = frame["recorded_success"]
    reason = frame["stop_reason"]
    if type(native) is not bool or (recorded is not None and type(recorded) is not bool):
        raise ValueError("native frame outcome signals must be boolean or null when unrecorded")
    if reason is not None and (not isinstance(reason, str) or reason not in {"goal", "horizon", "other"}):
        raise ValueError("native frame has an invalid stop reason")
    return {
        "state_sha256": _digest(state),
        "observation_sha256": {key: _digest(value) for key, value in observation.items()},
        "native_success": frame["native_success"],
        "stop_reason": frame["stop_reason"],
        "recorded_success": frame["recorded_success"],
    }


def replay_native_fixture(
    *,
    fixture: Mapping[str, Any],
    actions: Sequence[Any],
    expected: Sequence[Mapping[str, Any]],
    restore: Callable[[], Mapping[str, Any]],
    step: Callable[[Any], Mapping[str, Any]],
) -> dict[str, Any]:
    """Replay frozen actions through the native evaluator and locate divergence.

    The caller owns a fresh environment and captures actual state, observation
    fields, and outcome signals. Expected signatures include reset (step zero)
    and each post-action frame from the independently frozen reference.
    """
    if len(expected) != len(actions) + 1:
        raise ValueError("reference must cover reset and every saved action")
    actions_sha256 = _digest(actions)
    reference_sha256 = _digest(expected)
    samples = []
    differences = []
    frame = restore()
    for tick, reference in enumerate(expected):
        signature = native_frame_signature(frame)
        if _digest(signature) != _digest(reference):
            observed_fields = signature["observation_sha256"]
            reference_fields = reference.get("observation_sha256", {})
            if not isinstance(reference_fields, dict):
                raise ValueError("reference observation fingerprints must be a mapping")
            differences.append({
                "step": tick,
                "observation_fields": sorted(
                    key for key in observed_fields.keys() | reference_fields.keys()
                    if observed_fields.get(key) != reference_fields.get(key)
                ),
                "changed_signals": sorted(
                    key for key in signature if key != "observation_sha256"
                    and (key not in reference or _digest(signature[key]) != _digest(reference[key]))
                ),
            })
        samples.append({
            "step": tick,
            "state": json.loads(json.dumps(frame["state"], allow_nan=False)),
            "native_success": frame["native_success"],
            "stop_reason": frame["stop_reason"],
        })
        if tick == len(actions):
            break
        if frame["stop_reason"] is not None:
            differences.append({"step": tick, "reason": "terminated_before_reference_end"})
            break
        frame = step(actions[tick])
    qualification_fixture = None
    if not differences:
        qualification_fixture = {
            **fixture,
            "recorded_success": frame["recorded_success"],
            "samples": samples,
        }
    return {
        "schema": "benchstudio.native_evaluator_replay.v1",
        "passed": not differences,
        "actions_sha256": actions_sha256,
        "reference_sha256": reference_sha256,
        "first_mismatch_step": differences[0]["step"] if differences else None,
        "differences": differences,
        "qualification_fixture": qualification_fixture,
    }
