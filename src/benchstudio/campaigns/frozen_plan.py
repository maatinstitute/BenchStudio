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
    environment_id: str = "default"


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
    protocol: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FrozenCampaignPlan":
        """Reconstruct and validate a serialized frozen plan without execution."""
        if not isinstance(payload, dict):
            raise ValueError("frozen campaign plan must be a mapping")
        attempts_payload = payload.get("attempts")
        if not isinstance(attempts_payload, list):
            raise ValueError("frozen campaign plan attempts must be a list")
        attempts: list[PlannedAttempt] = []
        for index, item in enumerate(attempts_payload):
            if not isinstance(item, dict):
                raise ValueError(f"attempt {index} must be a mapping")
            key_payload = item.get("key")
            if not isinstance(key_payload, dict):
                raise ValueError(f"attempt {index} key must be a mapping")
            try:
                key = AttemptKey(**key_payload)
                metadata = item.get("metadata", {})
                if not isinstance(metadata, dict):
                    raise ValueError("metadata must be a mapping")
                attempt = PlannedAttempt(
                    key=key,
                    task_seed=int(item["task_seed"]),
                    policy_seed=int(item["policy_seed"]),
                    metadata=dict(metadata),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid attempt {index}: {exc}") from exc
            attempts.append(attempt)
        run_id = payload.get("run_id")
        digest = payload.get("plan_digest_sha256")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("frozen campaign plan run_id is required")
        if not isinstance(digest, str):
            raise ValueError("frozen campaign plan digest is required")
        protocol = payload.get("protocol")
        if protocol is not None and not isinstance(protocol, dict):
            raise ValueError("frozen campaign plan protocol must be a mapping")
        expected = _plan_digest(attempts, protocol)
        if expected != digest:
            raise ValueError("frozen campaign plan digest does not match content")
        paired_schedule = payload.get("paired_schedule", ())
        if not isinstance(paired_schedule, list) or not all(
            isinstance(item, dict) for item in paired_schedule
        ):
            raise ValueError("frozen campaign plan paired_schedule must be a list of mappings")
        source_spec_sha256 = payload.get("source_spec_sha256")
        if source_spec_sha256 is not None and not isinstance(source_spec_sha256, str):
            raise ValueError("source_spec_sha256 must be a string or null")
        return cls(
            run_id,
            tuple(attempts),
            digest,
            tuple(dict(item) for item in paired_schedule),
            source_spec_sha256,
            dict(protocol) if protocol is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "attempts": [asdict(item) for item in self.attempts],
            "plan_digest_sha256": self.plan_digest_sha256,
            "paired_schedule": list(self.paired_schedule),
            "source_spec_sha256": self.source_spec_sha256,
            "protocol": self.protocol,
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
        environment_ids: Iterable[str] = ("default",),
        protocol: dict[str, Any] | None = None,
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
        self.environment_ids = tuple(environment_ids)
        self.protocol = dict(protocol) if protocol is not None else None
        if not self.conditions or not self.seeds:
            raise ValueError("conditions and seeds must not be empty")
        if not self.environment_ids or any(
            not isinstance(environment_id, str) or not environment_id
            for environment_id in self.environment_ids
        ):
            raise ValueError("environment_ids must contain non-empty strings")
        if len(set(self.environment_ids)) != len(self.environment_ids):
            raise ValueError("environment_ids must be unique")

    def freeze(self) -> FrozenCampaignPlan:
        attempts: list[PlannedAttempt] = []
        for environment_id in self.environment_ids:
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
                                    self.run_id,
                                    self.scenario_id,
                                    pair_id,
                                    condition_id,
                                    attempt_id,
                                    environment_id,
                                ),
                                task_seed=seed,
                                policy_seed=seed + repetition,
                                metadata={
                                    "condition": condition,
                                    "seed_index": seed_index,
                                    "repetition": repetition,
                                    "scenario_pack_digest": self.scenario_pack_digest,
                                    "environment_id": environment_id,
                                },
                            )
                        )
        payload = {"attempts": [asdict(attempt) for attempt in attempts], "protocol": self.protocol}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return FrozenCampaignPlan(
            self.run_id,
            tuple(attempts),
            digest,
            source_spec_sha256=self.source_spec_sha256,
            protocol=self.protocol,
        )


def _identity(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]


def _plan_digest(attempts: Iterable[PlannedAttempt], protocol: dict[str, Any] | None) -> str:
    payload = {"attempts": [asdict(attempt) for attempt in attempts], "protocol": protocol}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_frozen_campaign_plan(path: Path) -> FrozenCampaignPlan:
    """Load and digest-validate a frozen campaign plan from JSON."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid frozen campaign plan: {exc}") from exc
    return FrozenCampaignPlan.from_dict(payload)
