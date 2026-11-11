"""Dependency-light single-call inference smoke measurement."""
from __future__ import annotations
import shutil, subprocess, time
from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True)
class InferenceSmokeResult:
    status: str
    elapsed_ns: int
    output_type: str | None
    gpu_memory_before_bytes: int | None
    gpu_memory_after_bytes: int | None
    error: str | None = None
    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

def _gpu_free(index: int = 0) -> int | None:
    command = shutil.which("nvidia-smi")
    if command is None: return None
    try:
        out = subprocess.run([command, f"--id={index}", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], check=True, capture_output=True, text=True, timeout=3).stdout.strip()
        return int(out.splitlines()[0]) * 1024 * 1024
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return None

def measure_inference(call: Callable[[], Any], *, gpu_index: int = 0) -> InferenceSmokeResult:
    before = _gpu_free(gpu_index)
    started = time.perf_counter_ns()
    try:
        output = call()
    except Exception as exc:  # noqa: BLE001 - smoke reports the failure
        return InferenceSmokeResult("failed", time.perf_counter_ns() - started, None, before, _gpu_free(gpu_index), repr(exc))
    return InferenceSmokeResult("completed", time.perf_counter_ns() - started, type(output).__name__, before, _gpu_free(gpu_index))
