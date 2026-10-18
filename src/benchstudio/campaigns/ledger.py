from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .frozen_plan import AttemptKey, FrozenCampaignPlan


class AttemptLedger:
    """Append-only result ledger that rejects reassignment and duplicate attempts."""

    def __init__(self, path: Path, plan: FrozenCampaignPlan) -> None:
        self.path = path
        self.plan = plan
        self._planned = {attempt.key.attempt_id: attempt.key for attempt in plan.attempts}
        self._seen: set[str] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = json.loads(line)
                    attempt_id = record.get("attempt_id")
                    if record.get("plan_digest_sha256") != plan.plan_digest_sha256:
                        raise ValueError("ledger record does not match frozen plan digest")
                    if not isinstance(attempt_id, str) or attempt_id not in self._planned:
                        raise ValueError("ledger contains an attempt outside the frozen plan")
                    expected = self._planned[attempt_id]
                    if any(
                        record.get(field) != getattr(expected, field)
                        for field in (
                            "run_id",
                            "scenario_id",
                            "pair_id",
                            "condition_id",
                            "environment_id",
                        )
                    ):
                        raise ValueError("ledger record identity does not match frozen plan")
                    if attempt_id in self._seen:
                        raise ValueError(f"ledger contains duplicate attempt: {attempt_id}")
                    self._seen.add(attempt_id)
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, key: AttemptKey, result: dict[str, Any]) -> None:
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

    def contains(self, attempt_id: str) -> bool:
        return attempt_id in self._seen

    @property
    def missing_attempt_ids(self) -> list[str]:
        return [
            attempt.key.attempt_id
            for attempt in self.plan.attempts
            if attempt.key.attempt_id not in self._seen
        ]

    @property
    def records(self) -> tuple[dict[str, Any], ...]:
        """Return the append-only records in ledger order for auditing."""
        if not self.path.is_file():
            return ()
        return tuple(
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
