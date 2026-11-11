"""Conservative, dependency-free hardware preflight for existing execution paths.

This module performs admission checks; it does not reserve memory, move tensors,
change simulator fidelity, or assert that estimates equal observed peak usage.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_MIB = 1024 * 1024


class ResourceAdmissionError(ValueError):
    """A declared per-worker footprint cannot be admitted on this host."""


@dataclass(frozen=True)
class GPUMemory:
    index: int
    total_bytes: int
    available_bytes: int

    def __post_init__(self) -> None:
        for name in ("index", "total_bytes", "available_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"GPU {name} must be a non-negative integer")
        if self.available_bytes > self.total_bytes:
            raise ValueError("GPU available_bytes exceeds total_bytes")

    def to_dict(self) -> dict[str, int]:
        return {
            "index": self.index,
            "total_bytes": self.total_bytes,
            "available_bytes": self.available_bytes,
        }


@dataclass(frozen=True)
class HardwareSnapshot:
    logical_cpus: int
    total_ram_bytes: int | None
    available_ram_bytes: int | None
    gpus: tuple[GPUMemory, ...] = ()
    gpu_probe_status: str = "unavailable"

    def __post_init__(self) -> None:
        if (
            isinstance(self.logical_cpus, bool)
            or not isinstance(self.logical_cpus, int)
            or self.logical_cpus < 1
        ):
            raise ValueError("logical_cpus must be a positive integer")
        for name in ("total_ram_bytes", "available_ram_bytes"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if self.total_ram_bytes is not None and self.available_ram_bytes is not None:
            if self.available_ram_bytes > self.total_ram_bytes:
                raise ValueError("available_ram_bytes exceeds total_ram_bytes")
        if len({gpu.index for gpu in self.gpus}) != len(self.gpus):
            raise ValueError("duplicate GPU indices")

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_cpus": self.logical_cpus,
            "total_ram_bytes": self.total_ram_bytes,
            "available_ram_bytes": self.available_ram_bytes,
            "gpus": [gpu.to_dict() for gpu in self.gpus],
            "gpu_probe_status": self.gpu_probe_status,
        }


@dataclass(frozen=True)
class ResourceRequest:
    """Caller-provided *estimates* of additional bytes needed by one worker.

    gpu_index=None chooses a suitable GPU if gpu_memory_bytes > 0, but never
    silently moves a GPU workload to CPU or changes the declared simulator.
    """

    host_memory_bytes: int = 0
    gpu_memory_bytes: int = 0
    gpu_index: int | None = None

    def __post_init__(self) -> None:
        for name in ("host_memory_bytes", "gpu_memory_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.gpu_index is not None:
            if (
                isinstance(self.gpu_index, bool)
                or not isinstance(self.gpu_index, int)
                or self.gpu_index < 0
            ):
                raise ValueError("gpu_index must be a non-negative integer or None")
            if self.gpu_memory_bytes == 0:
                raise ValueError("gpu_index requires positive gpu_memory_bytes")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ResourceRequest:
        if not isinstance(value, Mapping):
            raise ValueError("execution.resource_request must be a mapping")
        unknown = set(value) - {"host_memory_bytes", "gpu_memory_bytes", "gpu_index"}
        if unknown:
            raise ValueError(
                "unknown execution.resource_request fields: "
                + ", ".join(sorted(map(str, unknown)))
            )
        return cls(**value)

    def to_dict(self) -> dict[str, int | None]:
        return {
            "host_memory_bytes": self.host_memory_bytes,
            "gpu_memory_bytes": self.gpu_memory_bytes,
            "gpu_index": self.gpu_index,
        }


@dataclass(frozen=True)
class ResourcePlan:
    request: ResourceRequest
    hardware: HardwareSnapshot
    selected_gpu_index: int | None
    max_parallel_workers: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "benchstudio.resource_preflight.v1",
            "status": "admitted_estimate",
            "request": self.request.to_dict(),
            "hardware": self.hardware.to_dict(),
            "selected_gpu_index": self.selected_gpu_index,
            "max_parallel_workers": self.max_parallel_workers,
            "note": (
                "Admission uses caller estimates and a point-in-time snapshot; "
                "no memory is reserved."
            ),
        }


def plan_execution_resources(
    request: ResourceRequest, hardware: HardwareSnapshot
) -> ResourcePlan:
    """Reject estimated overcommit before policy/simulator construction.

    Returned capacity is an upper bound for workers coordinated *by one*
    CampaignExecutor, not a cross-process lock or a memory guarantee.
    """
    limits: list[int] = []
    if request.host_memory_bytes:
        available = hardware.available_ram_bytes
        if available is None:
            raise ResourceAdmissionError("host available memory is unknown")
        if request.host_memory_bytes > available:
            raise ResourceAdmissionError("declared host memory exceeds available RAM")
        limits.append(available // request.host_memory_bytes)

    gpu_index: int | None = None
    if request.gpu_memory_bytes:
        candidates = hardware.gpus
        if request.gpu_index is not None:
            candidates = tuple(gpu for gpu in candidates if gpu.index == request.gpu_index)
            if not candidates:
                raise ResourceAdmissionError(f"requested GPU {request.gpu_index} is unavailable")
        fitting = [gpu for gpu in candidates if gpu.available_bytes >= request.gpu_memory_bytes]
        if not fitting:
            raise ResourceAdmissionError("declared GPU memory exceeds available VRAM")
        # Deterministic preference: most free memory, then lowest device index.
        gpu = min(fitting, key=lambda item: (-item.available_bytes, item.index))
        gpu_index = gpu.index
        limits.append(gpu.available_bytes // request.gpu_memory_bytes)

    return ResourcePlan(
        request=request,
        hardware=hardware,
        selected_gpu_index=gpu_index,
        max_parallel_workers=min(limits) if limits else None,
    )


def probe_hardware() -> HardwareSnapshot:
    """Read host RAM and optional NVIDIA telemetry without importing AI runtimes."""
    total, available = _host_memory()
    gpus, status = _nvidia_gpus()
    return HardwareSnapshot(
        logical_cpus=os.cpu_count() or 1,
        total_ram_bytes=total,
        available_ram_bytes=available,
        gpus=gpus,
        gpu_probe_status=status,
    )


def _parse_meminfo(text: str) -> tuple[int | None, int | None]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, sep, raw = line.partition(":")
        if sep and key in {"MemTotal", "MemAvailable"}:
            parts = raw.strip().split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1] == "kB":
                values[key] = int(parts[0]) * 1024
    return values.get("MemTotal"), values.get("MemAvailable")


def _host_memory() -> tuple[int | None, int | None]:
    total: int | None = None
    available: int | None = None
    if platform.system() == "Linux":
        try:
            total, available = _parse_meminfo(Path("/proc/meminfo").read_text(encoding="utf-8"))
        except OSError:
            pass
        # Respect cgroup v2 limits in containerized workers.
        try:
            limit_raw = Path("/sys/fs/cgroup/memory.max").read_text().strip()
            usage_raw = Path("/sys/fs/cgroup/memory.current").read_text().strip()
            if limit_raw.isdecimal() and usage_raw.isdecimal():
                limit, usage = int(limit_raw), int(usage_raw)
                total = min(total, limit) if total is not None else limit
                free_in_cgroup = max(0, limit - usage)
                available = (
                    min(available, free_in_cgroup)
                    if available is not None
                    else free_in_cgroup
                )
        except OSError:
            pass
    if total is None and hasattr(os, "sysconf"):
        try:
            total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (ValueError, OSError, TypeError):
            pass
    return total, available


def _parse_nvidia_smi(text: str) -> tuple[GPUMemory, ...]:
    devices = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [value.strip() for value in line.split(",")]
        if len(parts) != 3 or not all(part.isdecimal() for part in parts):
            raise ValueError("unexpected NVIDIA memory telemetry")
        index, total_mib, free_mib = map(int, parts)
        devices.append(GPUMemory(index, total_mib * _MIB, free_mib * _MIB))
    return tuple(devices)


def _nvidia_gpus() -> tuple[tuple[GPUMemory, ...], str]:
    command = shutil.which("nvidia-smi")
    if command is None:
        return (), "nvidia_smi_not_found"
    try:
        result = subprocess.run(
            [
                command,
                "--query-gpu=index,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            text=True,
            capture_output=True,
            timeout=3,
        )
        devices = _parse_nvidia_smi(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return (), "nvidia_smi_failed"
    return devices, "nvidia_smi" if devices else "nvidia_smi_empty"
