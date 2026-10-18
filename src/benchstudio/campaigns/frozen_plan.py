from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class AttemptKey:
    run_id: str
    scenario_id: str
    pair_id: str
    condition_id: str
    attempt_id: str


@dataclass(frozen=True)
class PlannedAttempt:
    key: AttemptKey
    task_seed: int
    policy_seed: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class FrozenCampaignPlan:
    run_id: str
    attempts: tuple[PlannedAttempt, ...]
    plan_digest_sha256: str
    paired_schedule: tuple[dict[str, Any], ...] = ()
    source_spec_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "attempts": [asdict(item) for item in self.attempts],
            "plan_digest_sha256": self.plan_digest_sha256,
            "paired_schedule": list(self.paired_schedule),
            "source_spec_sha256": self.source_spec_sha256,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


class CampaignPlanner:
    """Create an immutable matrix before execution begins."""

    def __init__(
        self,
        *,
        run_id: str,
        scenario_id: str,
        conditions: Iterable[dict[str, Any]],
        seeds: Iterable[int],
        repetitions: int = 1,
        scenario_pack_digest: str | None = None,
        source_spec_sha256: str | None = None,
    ) -> None:
        if not run_id or not scenario_id:
            raise ValueError("run_id and scenario_id are required")
        if repetitions < 1:
            raise ValueError("repetitions must be positive")
        self.run_id = run_id
        self.scenario_id = scenario_id
        self.conditions = tuple(dict(condition) for condition in conditions)
        self.seeds = tuple(int(seed) for seed in seeds)
        self.repetitions = repetitions
        self.scenario_pack_digest = scenario_pack_digest
        self.source_spec_sha256 = source_spec_sha256
        if not self.conditions or not self.seeds:
            raise ValueError("conditions and seeds must not be empty")

    def freeze(self) -> FrozenCampaignPlan:
        attempts: list[PlannedAttempt] = []
        for condition in self.conditions:
            condition_id = _identity(condition)
            for seed_index, seed in enumerate(self.seeds):
                pair_id = _identity(
                    {
                        "scenario_id": self.scenario_id,
                        "scenario_pack_digest": self.scenario_pack_digest,
                        "seed": seed,
                    }
                )
                for repetition in range(self.repetitions):
                    attempt_id = f"attempt-{len(attempts):06d}"
                    attempts.append(
                        PlannedAttempt(
                            key=AttemptKey(
                                self.run_id, self.scenario_id, pair_id, condition_id, attempt_id
                            ),
                            task_seed=seed,
                            policy_seed=seed + repetition,
                            metadata={
                                "condition": condition,
                                "seed_index": seed_index,
                                "repetition": repetition,
                                "scenario_pack_digest": self.scenario_pack_digest,
                            },
                        )
                    )
        payload = [asdict(attempt) for attempt in attempts]
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return FrozenCampaignPlan(
            self.run_id,
            tuple(attempts),
            digest,
            source_spec_sha256=self.source_spec_sha256,
        )


def _identity(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
