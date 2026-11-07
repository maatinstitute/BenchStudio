"""Versioned replay inputs and runtime requirements for the public pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .robopad import RoboPADReplay, _file, _sha

_NAME = "benchstudio-replay.json"
_SCHEMA = "benchstudio.replay_manifest.v1"
_ADAPTER = "robopad.validation_transfer_v1"
_RENDERER_KEYS = {"vendor", "renderer", "version"}
_ENV_KEYS = {"MUJOCO_GL", "PYOPENGL_PLATFORM"}
_MODULE_KEYS = {"lerobot", "libero", "mujoco", "robosuite", "numpy"}


def _requirements(value: Any, allowed: set[str], name: str) -> dict[str, str]:
    if not isinstance(value, dict) or not set(value).issubset(allowed) or any(
        not isinstance(item, str) or not item.strip() for item in value.values()
    ):
        raise ValueError(f"invalid replay manifest {name}")
    return value


class ReplayEnvironmentError(ValueError):
    """A replay was blocked by the readiness check. Details are in report."""

    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        details = "; ".join(
            f"{row['field']}: {row['hint']}" for row in report["mismatches"]
        )
        super().__init__(f"replay environment is not ready. {details}")


@dataclass(frozen=True)
class ReplayManifest:
    adapter: str
    episode: str | None
    python: str | None = None
    modules: dict[str, str] | None = None
    renderer: dict[str, str] | None = None
    variables: dict[str, str] | None = None
    requirements_file: str | None = None
    pinned: bool = False

    @classmethod
    def open(
        cls, root: Path, requested_episode: str | None, *, trusted_sha256: str | None = None
    ) -> ReplayManifest:
        if trusted_sha256 is not None and (
            not isinstance(trusted_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", trusted_sha256)
        ):
            raise ValueError("trusted replay requires a lowercase SHA-256 manifest digest")
        source = root / _NAME
        if not source.exists() and not source.is_symlink():
            if trusted_sha256 is not None:
                raise ValueError("trusted replay requires benchstudio-replay.json")
            return cls(_ADAPTER, requested_episode)

        raw = _file(root, _NAME).read_bytes()
        if trusted_sha256 is not None and hashlib.sha256(raw).hexdigest() != trusted_sha256:
            raise ValueError("replay manifest differs from the independently trusted digest")
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError("replay manifest must be a JSON object")
        if document.get("schema") != _SCHEMA or document.get("adapter") != _ADAPTER:
            raise ValueError("unsupported BenchStudio replay manifest schema or adapter")
        episode = document.get("episode")
        if not isinstance(episode, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", episode):
            raise ValueError("the replay manifest must select a valid episode key")
        if requested_episode is not None and requested_episode != episode:
            raise ValueError("requested episode differs from the replay manifest")

        runtime = document.get("runtime")
        if not isinstance(runtime, dict):
            raise ValueError("versioned replay manifest requires a runtime declaration")
        python = runtime.get("python")
        if not isinstance(python, str) or not re.fullmatch(r"\d+\.\d+\.\d+", python):
            raise ValueError("replay manifest requires an exact Python version")
        modules = _requirements(runtime.get("modules"), _MODULE_KEYS, "modules")
        renderer = _requirements(runtime.get("renderer"), _RENDERER_KEYS, "renderer")
        variables = _requirements(runtime.get("variables", {}), _ENV_KEYS, "variables")
        if not modules or not {"vendor", "renderer"}.issubset(renderer):
            raise ValueError("pin imported module versions and the active renderer vendor and name")

        files = {
            "manifest.json",
            f"prepared/{episode}/record.json",
            f"evaluations/{episode}/base/record.json",
        }
        requirements_file = runtime.get("requirements_file")
        if requirements_file is not None:
            if not isinstance(requirements_file, str):
                raise ValueError("invalid replay manifest requirements file")
            lock = Path(requirements_file)
            if lock.is_absolute() or ".." in lock.parts or lock.suffix != ".txt":
                raise ValueError("requirements file must be a relative .txt lockfile")
            files.add(requirements_file)
        evidence = document.get("evidence_sha256")
        if not isinstance(evidence, dict) or set(evidence) != files:
            raise ValueError("replay manifest must bind the campaign, records and declared lockfile")
        for name in sorted(files):
            if evidence[name] != _sha(_file(root, name)):
                raise ValueError(f"replay manifest evidence digest mismatch: {name}")
        return cls(_ADAPTER, episode, python, modules, renderer, variables, requirements_file, True)

    def check(self, attempt: RoboPADReplay) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        mismatches: list[dict[str, Any]] = []
        setup = (
            f"Inspect and install the archived lockfile {self.requirements_file} in a fresh environment."
            if self.requirements_file else
            "Use the Python environment that produced the archived RoboPAD attempt."
        )

        def compare(field: str, expected: str, actual: str | None, hint: str) -> None:
            row = {"field": field, "expected": expected, "actual": actual}
            if expected == actual:
                matches.append(row)
            else:
                mismatches.append({**row, "hint": hint})

        if self.python is not None:
            compare("python", self.python, platform.python_version(), f"Use Python {self.python}.")
        for key, expected in sorted((self.variables or {}).items()):
            compare(key, expected, os.getenv(key), f"Set {key}={expected} before launching Python.")

        probe = {}
        if not mismatches:
            try:
                probe = (
                    attempt.check(inspect_renderer=True) if self.pinned else attempt.check()
                )
            except (OSError, AttributeError, ImportError, RuntimeError, TypeError, ValueError) as exc:
                mismatches.append({
                    "field": "native_reset", "expected": "successful reset and render",
                    "actual": str(exc), "hint": f"{exc}. {setup}",
                })
            else:
                for key, expected in sorted((self.modules or {}).items()):
                    actual = probe.get("loaded_modules", {}).get(key, {}).get("version")
                    compare(f"module.{key}", expected, actual, f"Use {key} {expected}. {setup}")
                for key, expected in sorted((self.renderer or {}).items()):
                    actual = (probe.get("active_renderer") or {}).get(key)
                    compare(
                        f"renderer.{key}", expected, actual,
                        f"Start the native stack with active OpenGL {key} {expected!r} and recheck.",
                    )
        return {
            **probe,
            "episode": attempt.episode,
            "adapter": self.adapter,
            "ready": not mismatches,
            "environment_profile": "pinned" if self.pinned else "legacy_unpinned",
            "matches": matches,
            "mismatches": mismatches,
            "setup": setup,
            "notes": [] if self.pinned else [
                "Legacy archive has no runtime pins. A successful reset alone does not establish parity."
            ],
        }

