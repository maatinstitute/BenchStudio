from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class WorkerLease:
    attempt_id: str
    worker_id: str
    expires_at_ns: int


class WorkerLeaseManager:
    """Filesystem-backed exclusive leases; physical jobs must disable retries upstream."""

    def __init__(
        self,
        root: Path,
        *,
        lease_seconds: float = 300.0,
        clock_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, (int, float))
            or not math.isfinite(lease_seconds)
            or lease_seconds <= 0
        ):
            raise ValueError("lease_seconds must be a finite positive number")
        self.root = root
        self.lease_seconds = lease_seconds
        self.clock_ns = clock_ns
        root.mkdir(parents=True, exist_ok=True)

    def acquire(self, attempt_id: str, worker_id: str) -> WorkerLease | None:
        _validate_identity(attempt_id, "attempt_id")
        _validate_identity(worker_id, "worker_id")
        path = self._path(attempt_id)
        now = self.clock_ns()
        _validate_timestamp(now, "clock_ns()")
        lease = WorkerLease(attempt_id, worker_id, now + int(self.lease_seconds * 1_000_000_000))
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(lease.__dict__, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            current = self._read_lease(path, attempt_id)
            if current is None:
                return None
            if current.expires_at_ns > now:
                return None
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return self.acquire(attempt_id, worker_id)
        return lease

    def renew(self, lease: WorkerLease) -> WorkerLease:
        """Extend an owned lease and return its new immutable lease record."""
        _validate_identity(lease.attempt_id, "attempt_id")
        _validate_identity(lease.worker_id, "worker_id")
        _validate_timestamp(lease.expires_at_ns, "expires_at_ns")
        path = self._path(lease.attempt_id)
        current = self._read_lease(path, lease.attempt_id)
        if current is None:
            raise ValueError("lease file is missing or invalid")
        if current.worker_id != lease.worker_id:
            raise ValueError("only the lease owner may renew a worker lease")
        now = self.clock_ns()
        _validate_timestamp(now, "clock_ns()")
        renewed = WorkerLease(
            lease.attempt_id,
            lease.worker_id,
            max(current.expires_at_ns, now) + int(self.lease_seconds * 1_000_000_000),
        )
        with path.open("w", encoding="utf-8") as handle:
            json.dump(renewed.__dict__, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        return renewed

    def release(self, lease: WorkerLease) -> None:
        _validate_identity(lease.attempt_id, "attempt_id")
        _validate_identity(lease.worker_id, "worker_id")
        _validate_timestamp(lease.expires_at_ns, "expires_at_ns")
        path = self._path(lease.attempt_id)
        current = self._read_lease(path, lease.attempt_id)
        if current is None:
            raise ValueError("lease file is missing or invalid")
        if current.worker_id != lease.worker_id:
            raise ValueError("only the lease owner may release a worker lease")
        path.unlink()

    def _path(self, attempt_id: str) -> Path:
        safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in attempt_id)
        return self.root / f"{safe}.lease"

    @staticmethod
    def _read_lease(path: Path, attempt_id: str) -> WorkerLease | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("attempt_id") != attempt_id:
            return None
        worker_id = payload.get("worker_id")
        expires_at_ns = payload.get("expires_at_ns")
        if not isinstance(worker_id, str) or not worker_id:
            return None
        if isinstance(expires_at_ns, bool) or not isinstance(expires_at_ns, int):
            return None
        if expires_at_ns < 0:
            return None
        return WorkerLease(attempt_id, worker_id, expires_at_ns)


def _validate_identity(value: str, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")


def _validate_timestamp(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
