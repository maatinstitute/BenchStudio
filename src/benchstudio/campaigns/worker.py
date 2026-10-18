from __future__ import annotations

import json
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
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.root = root
        self.lease_seconds = lease_seconds
        self.clock_ns = clock_ns
        root.mkdir(parents=True, exist_ok=True)

    def acquire(self, attempt_id: str, worker_id: str) -> WorkerLease | None:
        path = self._path(attempt_id)
        now = self.clock_ns()
        lease = WorkerLease(attempt_id, worker_id, now + int(self.lease_seconds * 1_000_000_000))
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(lease.__dict__, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            if int(current.get("expires_at_ns", 0)) > now:
                return None
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return self.acquire(attempt_id, worker_id)
        return lease

    def renew(self, lease: WorkerLease) -> WorkerLease:
        """Extend an owned lease and return its new immutable lease record."""
        path = self._path(lease.attempt_id)
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("lease file is missing or invalid") from exc
        if current.get("worker_id") != lease.worker_id:
            raise ValueError("only the lease owner may renew a worker lease")
        now = self.clock_ns()
        renewed = WorkerLease(
            lease.attempt_id,
            lease.worker_id,
            max(int(current.get("expires_at_ns", 0)), now)
            + int(self.lease_seconds * 1_000_000_000),
        )
        with path.open("w", encoding="utf-8") as handle:
            json.dump(renewed.__dict__, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        return renewed

    def release(self, lease: WorkerLease) -> None:
        path = self._path(lease.attempt_id)
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("lease file is missing or invalid") from exc
        if current.get("worker_id") != lease.worker_id:
            raise ValueError("only the lease owner may release a worker lease")
        path.unlink()

    def _path(self, attempt_id: str) -> Path:
        safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in attempt_id)
        return self.root / f"{safe}.lease"
