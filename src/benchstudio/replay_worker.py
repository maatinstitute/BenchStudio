"""Resource-bounded Linux subprocess for BenchStudio archive replay."""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

_REPORT_BYTES = 16 * 1024**2


class ReplayWorkerError(RuntimeError):
    """The replay worker failed or exceeded an execution limit."""


@dataclass(frozen=True)
class ReplayLimits:
    """Linux worker limits. Memory is virtual address space, not GPU memory."""

    wall_seconds: float = 300
    cpu_seconds: int = 240
    memory_bytes: int = 16 * 1024**3
    max_file_bytes: int = 1024**3
    max_open_files: int = 256

    def __post_init__(self) -> None:
        if (
            isinstance(self.wall_seconds, bool)
            or not isinstance(self.wall_seconds, (int, float))
            or not math.isfinite(self.wall_seconds)
            or self.wall_seconds <= 0
        ):
            raise ValueError("wall_seconds must be finite and positive")
        for name in ("cpu_seconds", "memory_bytes", "max_file_bytes", "max_open_files"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


def _supervise(command: list[str], root: Path, timeout: float) -> int:
    environment = {**os.environ, "TMPDIR": str(root)}
    with (root / "worker.log").open("wb") as log:
        with subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            env=environment, start_new_session=True,
        ) as process:
            try:
                return process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                raise ReplayWorkerError(f"replay exceeded its {timeout:g}s wall-clock limit") from exc
            finally:
                # Keep native helper processes in the same cleanup boundary.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()


def execute_in_worker(request: dict[str, Any], limits: ReplayLimits) -> dict[str, Any]:
    if sys.platform != "linux":
        raise ReplayWorkerError("resource-limited replay workers require Linux")
    with TemporaryDirectory(prefix="benchstudio-worker-") as temporary:
        root = Path(temporary)
        (root / "request.json").write_text(
            json.dumps({**request, "limits": asdict(limits)}), encoding="utf-8"
        )
        code = _supervise(
            [sys.executable, "-c",
             "from benchstudio.replay_worker import _child_main; _child_main()", str(root)],
            root,
            limits.wall_seconds,
        )
        report = root / "result.json"
        if code or not report.is_file():
            raise ReplayWorkerError(f"replay worker exited with status {code}; no valid report")
        if report.stat().st_size > _REPORT_BYTES:
            raise ReplayWorkerError("replay worker exceeded its report size limit")
        try:
            payload = json.loads(report.read_bytes())
        except (UnicodeError, ValueError) as exc:
            raise ReplayWorkerError("replay worker returned an invalid report") from exc
        if not isinstance(payload, dict) or payload.get("status") not in {
            "ok", "environment_error", "invalid_input", "worker_error"
        }:
            raise ReplayWorkerError("replay worker returned an invalid report")
        return payload


def _apply_limits(limits: ReplayLimits) -> None:
    import resource

    for kind, soft, hard in (
        (resource.RLIMIT_CPU, limits.cpu_seconds, limits.cpu_seconds + 1),
        (resource.RLIMIT_AS, limits.memory_bytes, limits.memory_bytes),
        (resource.RLIMIT_FSIZE, limits.max_file_bytes, limits.max_file_bytes),
        (resource.RLIMIT_NOFILE, limits.max_open_files, limits.max_open_files),
        (resource.RLIMIT_CORE, 0, 0),
    ):
        _, inherited_hard = resource.getrlimit(kind)
        if inherited_hard != resource.RLIM_INFINITY:
            hard = min(hard, inherited_hard)
        resource.setrlimit(kind, (min(soft, hard), hard))


def _child_main() -> None:
    from .pipeline import ReplayPipeline
    from .replay_manifest import ReplayEnvironmentError

    root = Path(sys.argv[1])
    request = json.loads((root / "request.json").read_text(encoding="utf-8"))
    try:
        _apply_limits(ReplayLimits(**request["limits"]))
        pipeline = ReplayPipeline.from_archive(
            request["archive"], episode=request["episode"],
            trusted_manifest_sha256=request["trusted_manifest_sha256"],
        )
        if request["check_only"]:
            result = pipeline.check()
        else:
            replay = pipeline.run(verify_environment=request["verify_environment"])
            result = {"report": replay.report, "environment": replay.environment}
        response = {"status": "ok", "result": result}
    except ReplayEnvironmentError as exc:
        response = {"status": "environment_error", "report": exc.report}
    except (OSError, KeyError, TypeError, ValueError, ImportError) as exc:
        response = {"status": "invalid_input", "message": str(exc)}
    except Exception as exc:
        response = {"status": "worker_error", "message": f"{type(exc).__name__}: {exc}"}
    with (root / "result.json").open("w", encoding="utf-8") as stream:
        json.dump(response, stream, allow_nan=False)
