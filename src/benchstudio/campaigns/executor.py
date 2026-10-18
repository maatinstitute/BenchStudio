from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..contracts import Policy, Simulator
from ..runner import RunConfig, run_episodes
from .frozen_plan import FrozenCampaignPlan, PlannedAttempt
from .ledger import AttemptLedger

PolicyFactory = Callable[[PlannedAttempt], Policy]
SimulatorFactory = Callable[[PlannedAttempt], Simulator]


@dataclass(frozen=True)
class CampaignExecutionSummary:
    run_id: str
    plan_digest_sha256: str
    committed_attempt_ids: tuple[str, ...]
    skipped_attempt_ids: tuple[str, ...]
    missing_attempt_ids: tuple[str, ...]


class CampaignExecutor:
    """Execute exactly the attempts in a frozen plan with resumable commits."""

    def __init__(
        self,
        plan: FrozenCampaignPlan,
        output: Path,
        policy_factory: PolicyFactory,
        simulator_factory: SimulatorFactory,
    ) -> None:
        self.plan = plan
        self.output = output
        self.policy_factory = policy_factory
        self.simulator_factory = simulator_factory
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
        for attempt in self.plan.attempts:
            attempt_id = attempt.key.attempt_id
            if self.ledger.contains(attempt_id):
                skipped.append(attempt_id)
                continue
            attempt_dir = self.output / "attempts" / attempt_id
            if attempt_dir.exists():
                summary_path = attempt_dir / "summary.json"
                if not summary_path.is_file():
                    raise RuntimeError(
                        f"attempt {attempt_id} has partial evidence and cannot be silently retried"
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
            self.ledger.append(
                attempt.key,
                {
                    "status": summary.get("campaign_status"),
                    "success_count": summary.get("success_count"),
                    "scheduled_episode_count": summary.get("scheduled_episode_count"),
                    "completed_episode_count": summary.get("completed_episode_count"),
                    "attempt_summary_path": str(attempt_dir / "summary.json"),
                },
            )
            committed.append(attempt_id)
        return CampaignExecutionSummary(
            self.plan.run_id,
            self.plan.plan_digest_sha256,
            tuple(committed),
            tuple(skipped),
            tuple(self.ledger.missing_attempt_ids),
        )
