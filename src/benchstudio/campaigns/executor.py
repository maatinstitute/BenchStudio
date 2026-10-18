from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from ..contracts import Policy, Simulator
from ..evidence import verify_artifact_manifest
from ..runner import RunConfig, run_episodes
from .frozen_plan import FrozenCampaignPlan, PlannedAttempt
from .ledger import AttemptLedger
from .worker import WorkerLeaseManager

PolicyFactory = Callable[[PlannedAttempt], Policy]
SimulatorFactory = Callable[[PlannedAttempt], Simulator]


@dataclass(frozen=True)
class CampaignExecutionSummary:
    run_id: str
    plan_digest_sha256: str
    committed_attempt_ids: tuple[str, ...]
    skipped_attempt_ids: tuple[str, ...]
    missing_attempt_ids: tuple[str, ...]
    leased_out_attempt_ids: tuple[str, ...]
    cancelled_attempt_ids: tuple[str, ...]


class CampaignExecutor:
    """Execute exactly the attempts in a frozen plan with resumable commits."""

    def __init__(
        self,
        plan: FrozenCampaignPlan,
        output: Path,
        policy_factory: PolicyFactory,
        simulator_factory: SimulatorFactory,
        worker_id: str | None = None,
        lease_manager: WorkerLeaseManager | None = None,
        cancelled_attempts: Iterable[str] = (),
    ) -> None:
        self.plan = plan
        self.output = output
        self.policy_factory = policy_factory
        self.simulator_factory = simulator_factory
        self.worker_id = worker_id
        self.lease_manager = lease_manager
        self.cancelled_attempts = frozenset(cancelled_attempts)
        planned_ids = {attempt.key.attempt_id for attempt in plan.attempts}
        unknown = self.cancelled_attempts - planned_ids
        if unknown:
            raise ValueError(f"unknown cancelled attempts: {sorted(unknown)}")
        self.output.mkdir(parents=True, exist_ok=True)
        plan_path = self.output / "campaign-plan.json"
        if plan_path.is_file():
            existing = json.loads(plan_path.read_text(encoding="utf-8"))
            if existing.get("plan_digest_sha256") != plan.plan_digest_sha256:
                raise ValueError("existing campaign plan does not match frozen plan")
        else:
            self.plan.write(plan_path)
        self.ledger = AttemptLedger(self.output / "attempt-results.jsonl", plan)

    def run(self) -> CampaignExecutionSummary:
        committed: list[str] = []
        skipped: list[str] = []
        leased_out: list[str] = []
        cancelled: list[str] = []
        for attempt in self.plan.attempts:
            attempt_id = attempt.key.attempt_id
            if self.ledger.contains(attempt_id):
                attempt_dir = self.output / "attempts" / attempt_id
                verification = verify_artifact_manifest(attempt_dir)
                if not verification["valid"]:
                    raise RuntimeError(
                        f"attempt {attempt_id} evidence verification failed: "
                        f"{verification['mismatches']}"
                    )
                skipped.append(attempt_id)
                continue
            if attempt_id in self.cancelled_attempts:
                self.ledger.append(
                    attempt.key,
                    {"status": "cancelled", "reason": "cancelled_before_execution"},
                )
                cancelled.append(attempt_id)
                continue
            lease = None
            if self.worker_id is not None:
                if self.lease_manager is None:
                    raise ValueError("worker_id requires a lease_manager")
                lease = self.lease_manager.acquire(attempt_id, self.worker_id)
                if lease is None:
                    leased_out.append(attempt_id)
                    continue
            attempt_dir = self.output / "attempts" / attempt_id
            try:
                if attempt_dir.exists():
                    summary_path = attempt_dir / "summary.json"
                    if not summary_path.is_file():
                        raise RuntimeError(
                            f"attempt {attempt_id} has partial evidence and "
                            "cannot be silently retried"
                        )
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                else:
                    condition = attempt.metadata.get("condition", {})
                    config = RunConfig(
                        task_id=attempt.key.scenario_id,
                        seed=attempt.task_seed,
                        episodes=1,
                        denoising_steps=condition.get("denoising_steps", 2),
                        action_prefix=condition.get("action_prefix", 2),
                        observation_refresh_ticks=condition.get("observation_refresh_ticks", 1),
                        max_episode_steps=condition.get("max_episode_steps", 100),
                        initial_condition_id=attempt.key.pair_id,
                    )
                    summary = run_episodes(
                        self.policy_factory(attempt),
                        self.simulator_factory(attempt),
                        config,
                        attempt_dir,
                    )
                verification = verify_artifact_manifest(attempt_dir)
                if not verification["valid"]:
                    raise RuntimeError(
                        f"attempt {attempt_id} evidence verification failed: "
                        f"{verification['mismatches']}"
                    )
                self.ledger.append(
                    attempt.key,
                    {
                        "status": summary.get("campaign_status"),
                        "success_count": summary.get("success_count"),
                        "scheduled_episode_count": summary.get("scheduled_episode_count"),
                        "completed_episode_count": summary.get("completed_episode_count"),
                        "attempt_summary_path": str(attempt_dir / "summary.json"),
                        "evidence_verified": True,
                    },
                )
                committed.append(attempt_id)
            finally:
                if lease is not None:
                    self.lease_manager.release(lease)
        return CampaignExecutionSummary(
            self.plan.run_id,
            self.plan.plan_digest_sha256,
            tuple(committed),
            tuple(skipped),
            tuple(self.ledger.missing_attempt_ids),
            tuple(leased_out),
            tuple(cancelled),
        )
