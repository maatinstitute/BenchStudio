from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .frozen_plan import AttemptKey, FrozenCampaignPlan


class AttemptLedger:
    """Append-only result ledger that rejects reassignment and duplicate attempts."""

    def __init__(self, path: Path, plan: FrozenCampaignPlan) -> None:
        self.path = path
        self.lock_path = path.with_name(path.name + ".lock")
        self.plan = plan
        self._planned = {attempt.key.attempt_id: attempt.key for attempt in plan.attempts}
        self._seen: set[str] = set()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.touch(exist_ok=True)
        with self._locked():
            self._seen = self._load_seen()

    @contextmanager
    def _locked(self):
        """Serialize ledger reads and commits across worker processes."""
        with self.lock_path.open("r+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def _load_seen(self) -> set[str]:
        seen: set[str] = set()
        if not self.path.exists():
            return seen
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("ledger contains invalid JSON") from exc
            if not isinstance(record, dict):
                raise ValueError("ledger record must be a mapping")
            attempt_id = record.get("attempt_id")
            digest = record.get("plan_digest_sha256")
            if not isinstance(digest, str) or digest != self.plan.plan_digest_sha256:
                raise ValueError("ledger record does not match frozen plan digest")
            if not isinstance(attempt_id, str) or attempt_id not in self._planned:
                raise ValueError("ledger contains an attempt outside the frozen plan")
            expected = self._planned[attempt_id]
            identity_fields = (
                "run_id",
                "scenario_id",
                "pair_id",
                "condition_id",
                "environment_id",
            )
            if any(not isinstance(record.get(field), str) for field in identity_fields):
                raise ValueError("ledger record identity fields must be strings")
            if any(record.get(field) != getattr(expected, field) for field in identity_fields):
                raise ValueError("ledger record identity does not match frozen plan")
            if attempt_id in seen:
                raise ValueError(f"ledger contains duplicate attempt: {attempt_id}")
            seen.add(attempt_id)
        return seen

    def append(self, key: AttemptKey, result: dict[str, Any]) -> None:
        with self._locked():
            self._seen = self._load_seen()
            planned = self._planned.get(key.attempt_id)
            if planned is None:
                raise ValueError(f"attempt is not in frozen plan: {key.attempt_id}")
            if planned != key:
                raise ValueError(f"attempt identity does not match frozen plan: {key.attempt_id}")
            if key.attempt_id in self._seen:
                raise ValueError(f"attempt already recorded: {key.attempt_id}")
            record = {
                **result,
                "run_id": key.run_id,
                "scenario_id": key.scenario_id,
                "pair_id": key.pair_id,
                "condition_id": key.condition_id,
                "environment_id": key.environment_id,
                "attempt_id": key.attempt_id,
                "plan_digest_sha256": self.plan.plan_digest_sha256,
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._seen.add(key.attempt_id)

    def append_idempotent(self, key: AttemptKey, result: dict[str, Any]) -> bool:
        """Commit once, treating an identical concurrent commit as a no-op.

        Returns ``True`` when this call appended a new record and ``False``
        when another worker already committed the same result. A conflicting
        duplicate remains an error: idempotency must not hide divergent worker
        evidence for one frozen attempt.
        """
        try:
            self.append(key, result)
        except ValueError as exc:
            if "already recorded" not in str(exc):
                raise
            existing = self.record_for(key.attempt_id)
            if existing is None:
                raise RuntimeError(
                    f"attempt {key.attempt_id} disappeared during duplicate commit reconciliation"
                ) from exc
            if any(existing.get(field) != value for field, value in result.items()):
                raise ValueError(
                    f"conflicting duplicate commit for attempt {key.attempt_id}"
                ) from exc
            return False
        return True

    def contains(self, attempt_id: str) -> bool:
        with self._locked():
            self._seen = self._load_seen()
            return attempt_id in self._seen

    def record_for(self, attempt_id: str) -> dict[str, Any] | None:
        """Return one committed record, or ``None`` when it is still missing."""
        with self._locked():
            self._seen = self._load_seen()
            if not self.path.is_file():
                return None
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("attempt_id") == attempt_id:
                    return record
            return None

    @property
    def missing_attempt_ids(self) -> list[str]:
        with self._locked():
            self._seen = self._load_seen()
            return [
                attempt.key.attempt_id
                for attempt in self.plan.attempts
                if attempt.key.attempt_id not in self._seen
            ]

    @property
    def records(self) -> tuple[dict[str, Any], ...]:
        """Return the append-only records in ledger order for auditing."""
        with self._locked():
            self._seen = self._load_seen()
            if not self.path.is_file():
                return ()
            return tuple(
                json.loads(line)
                for line in self.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
