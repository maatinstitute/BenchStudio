from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

from ..analysis.resources import ResourceBudget
from ..contracts import Policy, Simulator
from ..evidence import verify_artifact_manifest
from ..measurement import ResourceSampler
from ..runner import RunConfig, run_episodes
from .frozen_plan import FrozenCampaignPlan, PlannedAttempt
from .ledger import AttemptLedger
from .worker import WorkerLeaseManager

if TYPE_CHECKING:
    from ..adapters import AdapterRegistry
    from ..analysis.campaign_audit import CampaignAudit
    from ..analysis.claims import ClaimType
    from ..analysis.outcomes import OutcomeRecord

PolicyFactory = Callable[[PlannedAttempt], Policy]
SimulatorFactory = Callable[[PlannedAttempt], Simulator]
ResourceSamplerFactory = Callable[[PlannedAttempt], ResourceSampler]


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
        resource_sampler_factory: ResourceSamplerFactory | None = None,
        adapter_registry: "AdapterRegistry | None" = None,
    ) -> None:
        self.plan = plan
        self.output = output
        self.policy_factory = policy_factory
        self.simulator_factory = simulator_factory
        self.worker_id = worker_id
        self.lease_manager = lease_manager
        self.cancelled_attempts = frozenset(cancelled_attempts)
        self.resource_sampler_factory = resource_sampler_factory
        if adapter_registry is not None:
            issues = adapter_registry.validate_plan(plan)
            if issues:
                raise ValueError(
                    "campaign backend requirements are not satisfied: " + "; ".join(issues)
                )
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
                        environment_id=attempt.key.environment_id,
                        seed=attempt.task_seed,
                        episodes=1,
                        denoising_steps=condition.get("denoising_steps", 2),
                        action_prefix=condition.get("action_prefix", 2),
                        observation_refresh_ticks=condition.get("observation_refresh_ticks", 1),
                        max_episode_steps=condition.get("max_episode_steps", 100),
                        initial_condition_id=attempt.key.pair_id,
                        resource_budget=_resource_budget(self.plan),
                    )
                    summary = run_episodes(
                        self.policy_factory(attempt),
                        self.simulator_factory(attempt),
                        config,
                        attempt_dir,
                        resource_sampler=(
                            self.resource_sampler_factory(attempt)
                            if self.resource_sampler_factory is not None
                            else None
                        ),
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
                        "resource_budget_audit": summary.get("resource_budget_audit"),
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

    def audit(
        self,
        *,
        claim_type: "ClaimType | None" = None,
        evidence: dict[str, Any] | None = None,
        outcome_records: Iterable["OutcomeRecord"] | None = None,
    ) -> "CampaignAudit":
        """Audit the current ledger against this executor's frozen plan."""
        from ..analysis.campaign_audit import audit_campaign
        from ..analysis.claims import ClaimType

        if claim_type is None:
            claim_type = ClaimType.SINGLE_RUN_OUTCOME
        return audit_campaign(
            self.plan,
            self.ledger.records,
            claim_type=claim_type,
            evidence=evidence,
            outcome_records=outcome_records,
        )

    def archive(self, destination: Path) -> dict[str, str | int]:
        """Write this campaign's current evidence as an immutable bundle."""
        from .archive import write_campaign_archive

        return write_campaign_archive(self.output, destination)


def _resource_budget(plan: FrozenCampaignPlan) -> ResourceBudget | None:
    evaluation = (plan.protocol or {}).get("P", {}).get("evaluation", {})
    values = evaluation.get("resource_budget", {})
    if not isinstance(values, dict):
        return None
    if not any(
        name in values for name in ("max_policy_calls", "max_wall_time_ms", "max_compute_time_ms")
    ):
        return None
    return ResourceBudget(
        max_inference_calls=values.get("max_policy_calls"),
        max_wall_time_ms=values.get("max_wall_time_ms"),
        max_compute_time_ms=values.get("max_compute_time_ms"),
    )
