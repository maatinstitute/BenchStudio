from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

from ..analysis.resources import ResourceBudget
from ..contracts import Policy, Simulator
from ..evidence import verify_artifact_manifest
from ..measurement import ResourceSampler
from ..runner import RunConfig, run_episodes
from ..runtime_receipts import load_runtime_receipt, verify_runtime_receipt
from .frozen_plan import FrozenCampaignPlan, PlannedAttempt, load_frozen_campaign_plan
from .ledger import AttemptLedger
from .worker import WorkerLeaseManager

if TYPE_CHECKING:
    from ..adapters import AdapterRegistry
    from ..analysis.campaign_audit import CampaignAudit
    from ..analysis.claims import ClaimType
    from ..analysis.outcomes import OutcomeRecord
    from ..model_adapters import ModelAdapterRegistry

PolicyFactory = Callable[[PlannedAttempt], Policy]
PolicyKwargsFactory = Callable[[PlannedAttempt], dict[str, Any]]
SimulatorFactory = Callable[[PlannedAttempt], Simulator]
SimulatorKwargsFactory = Callable[[PlannedAttempt], dict[str, Any]]
ResourceSamplerFactory = Callable[[PlannedAttempt], ResourceSampler]


@dataclass(frozen=True)
class CampaignExecutionSummary:
    run_id: str
    plan_digest_sha256: str
    committed_attempt_ids: tuple[str, ...]
    failed_attempt_ids: tuple[str, ...]
    skipped_attempt_ids: tuple[str, ...]
    missing_attempt_ids: tuple[str, ...]
    leased_out_attempt_ids: tuple[str, ...]
    cancelled_attempt_ids: tuple[str, ...]


class CampaignExecutor:
    """Execute exactly the attempts in a frozen plan with resumable commits."""

    @classmethod
    def from_plan_file(
        cls,
        plan_path: Path,
        output: Path,
        policy_factory: PolicyFactory | None = None,
        simulator_factory: SimulatorFactory | None = None,
        **kwargs: Any,
    ) -> "CampaignExecutor":
        """Construct an executor from an independently loaded frozen plan.

        This is the scheduler-facing entry point: the worker does not receive
        a mutable planner or reconstruct attempts from CLI flags. It loads and
        digest-validates the serialized plan, then the normal constructor
        binds that exact plan to the campaign output and ledger.
        """
        plan = load_frozen_campaign_plan(Path(plan_path))
        return cls(
            plan,
            Path(output),
            policy_factory=policy_factory,
            simulator_factory=simulator_factory,
            **kwargs,
        )

    def __init__(
        self,
        plan: FrozenCampaignPlan,
        output: Path,
        policy_factory: PolicyFactory | None = None,
        simulator_factory: SimulatorFactory | None = None,
        worker_id: str | None = None,
        lease_manager: WorkerLeaseManager | None = None,
        cancelled_attempts: Iterable[str] = (),
        resource_sampler_factory: ResourceSamplerFactory | None = None,
        adapter_registry: "AdapterRegistry | None" = None,
        simulator_kwargs_factory: SimulatorKwargsFactory | None = None,
        model_registry: "ModelAdapterRegistry | None" = None,
        policy_kwargs_factory: PolicyKwargsFactory | None = None,
    ) -> None:
        self.plan = plan
        self.output = output
        self.policy_factory = policy_factory
        self.model_registry = model_registry
        self.policy_kwargs_factory = policy_kwargs_factory
        self.simulator_factory = simulator_factory
        self.adapter_registry = adapter_registry
        self.simulator_kwargs_factory = simulator_kwargs_factory
        if simulator_factory is None and adapter_registry is None:
            raise ValueError("simulator_factory or adapter_registry is required")
        if policy_factory is None and model_registry is None:
            raise ValueError("policy_factory or model_registry is required")
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
        if model_registry is not None:
            issues = model_registry.validate_plan(plan)
            if issues:
                raise ValueError(
                    "campaign model requirements are not satisfied: " + "; ".join(issues)
                )
        _validate_execution_safety(plan)
        _validate_worldepisode_protocol(plan)
        planned_ids = {attempt.key.attempt_id for attempt in plan.attempts}
        unknown = self.cancelled_attempts - planned_ids
        if unknown:
            raise ValueError(f"unknown cancelled attempts: {sorted(unknown)}")
        self.output.mkdir(parents=True, exist_ok=True)
        plan_path = self.output / "campaign-plan.json"
        if plan_path.is_file():
            try:
                existing_plan = load_frozen_campaign_plan(plan_path)
            except ValueError as exc:
                raise ValueError("existing campaign plan is invalid") from exc
            if existing_plan != plan:
                raise ValueError("existing campaign plan does not match frozen plan")
        else:
            self.plan.write(plan_path)
        self.ledger = AttemptLedger(self.output / "attempt-results.jsonl", plan)

    def run(self, attempt_ids: Iterable[str] | None = None) -> CampaignExecutionSummary:
        """Execute all attempts or an explicit frozen subset.

        A subset is useful when an external scheduler assigns attempts to
        container or GPU workers. The subset is still checked against the
        frozen plan, and the shared ledger remains the authority for recovery.
        """
        selected_ids = (
            {attempt.key.attempt_id for attempt in self.plan.attempts}
            if attempt_ids is None
            else set(attempt_ids)
        )
        planned_ids = {attempt.key.attempt_id for attempt in self.plan.attempts}
        unknown = selected_ids - planned_ids
        if unknown:
            raise ValueError(f"attempt_ids are outside the frozen plan: {sorted(unknown)}")
        committed: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []
        leased_out: list[str] = []
        cancelled: list[str] = []
        for attempt in self.plan.attempts:
            attempt_id = attempt.key.attempt_id
            if attempt_id not in selected_ids:
                continue
            if self.ledger.contains(attempt_id):
                record = self.ledger.record_for(attempt_id)
                if record is None:
                    raise RuntimeError(f"ledger lost committed attempt {attempt_id}")
                if record.get("status") != "infrastructure_failure":
                    attempt_dir = self.output / "attempts" / attempt_id
                    self._verify_runtime_receipt(attempt, attempt_dir)
                    verification = verify_artifact_manifest(attempt_dir)
                    if not verification["valid"]:
                        raise RuntimeError(
                            f"attempt {attempt_id} evidence verification failed: "
                            f"{verification['mismatches']}"
                        )
                skipped.append(attempt_id)
                continue
            if attempt_id in self.cancelled_attempts:
                committed_now = self.ledger.append_idempotent(
                    attempt.key,
                    {"status": "cancelled", "reason": "cancelled_before_execution"},
                )
                (cancelled if committed_now else skipped).append(attempt_id)
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
                        run_id=attempt.key.run_id,
                        attempt_id=attempt.key.attempt_id,
                        plan_digest_sha256=self.plan.plan_digest_sha256,
                        worker_id=self.worker_id,
                        task_id=attempt.key.scenario_id,
                        environment_id=attempt.key.environment_id,
                        planned_condition_id=attempt.key.condition_id,
                        seed=attempt.task_seed,
                        episodes=1,
                        denoising_steps=condition.get("denoising_steps", 2),
                        action_prefix=condition.get("action_prefix", 2),
                        observation_refresh_ticks=condition.get("observation_refresh_ticks", 1),
                        max_episode_steps=condition.get("max_episode_steps", 100),
                        execution_strategy=condition.get(
                            "execution_strategy", _execution_strategy(self.plan)
                        ),
                        max_cache_entries=condition.get(
                            "max_cache_entries", _max_cache_entries(self.plan)
                        ),
                        calibration=_calibration(self.plan, attempt.key.environment_id),
                        benchmark_validity=_benchmark_validity(self.plan),
                        model_reference=_model_reference(self.plan),
                        initial_condition_id=attempt.key.pair_id,
                        resource_budget=_resource_budget(self.plan),
                    )
                    summary = run_episodes(
                        self._policy_for_attempt(attempt),
                        self._simulator_for_attempt(attempt),
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
                self._verify_runtime_receipt(attempt, attempt_dir)
                committed_now = self.ledger.append_idempotent(
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
                if not committed_now:
                    skipped.append(attempt_id)
                elif summary.get("campaign_status") == "completed":
                    committed.append(attempt_id)
                else:
                    failed.append(attempt_id)
            except Exception as exc:
                committed_failure = self.ledger.append_idempotent(
                    attempt.key,
                    {
                        "status": "infrastructure_failure",
                        "reason": "attempt_execution_exception",
                        "error": f"{type(exc).__name__}: {exc}",
                        "evidence_verified": False,
                    },
                )
                if committed_failure:
                    failed.append(attempt_id)
                else:
                    skipped.append(attempt_id)
            finally:
                if lease is not None:
                    self.lease_manager.release(lease)
        return CampaignExecutionSummary(
            self.plan.run_id,
            self.plan.plan_digest_sha256,
            tuple(committed),
            tuple(failed),
            tuple(skipped),
            tuple(self.ledger.missing_attempt_ids),
            tuple(leased_out),
            tuple(cancelled),
        )

    def _verify_runtime_receipt(self, attempt: PlannedAttempt, attempt_dir: Path) -> None:
        receipt_path = attempt_dir / "runtime-receipt.json"
        verification = verify_runtime_receipt(receipt_path)
        if not verification["valid"]:
            raise RuntimeError(
                f"attempt {attempt.key.attempt_id} runtime receipt is invalid: "
                f"{verification['reason']}"
            )
        receipt = load_runtime_receipt(receipt_path)
        expected = {
            "run_id": self.plan.run_id,
            "attempt_id": attempt.key.attempt_id,
            "plan_digest_sha256": self.plan.plan_digest_sha256,
        }
        for field, value in expected.items():
            if receipt.get(field) != value:
                raise RuntimeError(
                    f"attempt {attempt.key.attempt_id} runtime receipt {field} does not "
                    "match the frozen plan"
                )
        if receipt.get("worker_id") is not None and not isinstance(receipt.get("worker_id"), str):
            raise RuntimeError(
                f"attempt {attempt.key.attempt_id} runtime receipt worker identity is invalid"
            )

    def run_parallel(self, workers: int) -> CampaignExecutionSummary:
        """Run pending attempts with multiple lease-owning workers.

        Each worker gets its own executor and refreshes the shared append-only
        ledger before committing. The frozen plan remains the only work list;
        leases decide ownership and make this safe to resume after a worker
        exits.
        """
        if workers < 1:
            raise ValueError("workers must be positive")
        if workers == 1:
            return self.run()
        lease_root = (
            self.lease_manager.root if self.lease_manager is not None else self.output / "leases"
        )
        lease_seconds = (
            self.lease_manager.lease_seconds if self.lease_manager is not None else 300.0
        )
        worker_prefix = self.worker_id or self.plan.run_id

        def execute(worker_index: int) -> CampaignExecutionSummary:
            worker = CampaignExecutor(
                self.plan,
                self.output,
                policy_factory=self.policy_factory,
                simulator_factory=self.simulator_factory,
                worker_id=f"{worker_prefix}-{worker_index}",
                lease_manager=WorkerLeaseManager(lease_root, lease_seconds=lease_seconds),
                cancelled_attempts=self.cancelled_attempts,
                resource_sampler_factory=self.resource_sampler_factory,
                adapter_registry=self.adapter_registry,
                simulator_kwargs_factory=self.simulator_kwargs_factory,
                model_registry=self.model_registry,
                policy_kwargs_factory=self.policy_kwargs_factory,
            )
            return worker.run()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = tuple(pool.map(execute, range(workers)))

        order = {attempt.key.attempt_id: index for index, attempt in enumerate(self.plan.attempts)}
        committed = sorted(
            {attempt_id for result in results for attempt_id in result.committed_attempt_ids},
            key=order.__getitem__,
        )
        failed = sorted(
            {attempt_id for result in results for attempt_id in result.failed_attempt_ids},
            key=order.__getitem__,
        )
        skipped = sorted(
            {attempt_id for result in results for attempt_id in result.skipped_attempt_ids},
            key=order.__getitem__,
        )
        leased_out = sorted(
            {attempt_id for result in results for attempt_id in result.leased_out_attempt_ids},
            key=order.__getitem__,
        )
        cancelled = sorted(
            {attempt_id for result in results for attempt_id in result.cancelled_attempt_ids},
            key=order.__getitem__,
        )
        return CampaignExecutionSummary(
            self.plan.run_id,
            self.plan.plan_digest_sha256,
            tuple(committed),
            tuple(failed),
            tuple(skipped),
            tuple(self.ledger.missing_attempt_ids),
            tuple(leased_out),
            tuple(cancelled),
        )

    def _policy_for_attempt(self, attempt: PlannedAttempt) -> Policy:
        if self.policy_factory is not None:
            return self.policy_factory(attempt)
        if self.model_registry is None:
            raise RuntimeError("no policy factory or model registry is configured")
        model = self.plan.protocol.get("M", {})
        adapter_id = model.get("adapter") if isinstance(model, dict) else None
        if not isinstance(adapter_id, str) or not adapter_id:
            raise ValueError(
                "frozen plan requires model.adapter when no policy_factory is supplied"
            )
        kwargs = (
            self.policy_kwargs_factory(attempt)
            if self.policy_kwargs_factory is not None
            else model.get("adapter_config", {})
        )
        if not isinstance(kwargs, dict):
            raise ValueError("model.adapter_config must be a mapping")
        return self.model_registry.create(adapter_id, **kwargs)

    def _simulator_for_attempt(self, attempt: PlannedAttempt) -> Simulator:
        """Resolve a custom factory or the adapter declared by the frozen plan."""
        if self.simulator_factory is not None:
            return self.simulator_factory(attempt)
        if self.adapter_registry is None:  # guarded by __init__, explicit for typing
            raise RuntimeError("no simulator factory or adapter registry is configured")

        environments = self.plan.protocol.get("S", {}).get("environments", [])
        environment = next(
            (
                item
                for item in environments
                if isinstance(item, dict) and item.get("id") == attempt.key.environment_id
            ),
            None,
        )
        if environment is None:
            raise ValueError(
                f"frozen plan has no environment declaration for {attempt.key.environment_id!r}"
            )
        simulator_id = environment.get("adapter")
        if not isinstance(simulator_id, str) or not simulator_id:
            raise ValueError(
                f"environment {attempt.key.environment_id!r} requires an adapter "
                "when no simulator_factory is supplied"
            )
        if self.simulator_kwargs_factory is not None:
            kwargs = self.simulator_kwargs_factory(attempt)
        else:
            kwargs = environment.get("adapter_config", {})
        if not isinstance(kwargs, dict):
            raise ValueError(
                f"environment {attempt.key.environment_id!r} adapter_config must be a mapping"
            )
        required = environment.get("required_capabilities", {})
        return self.adapter_registry.create(
            simulator_id,
            required_capabilities=required,
            **kwargs,
        )

    def audit(
        self,
        *,
        claim_type: "ClaimType | None" = None,
        evidence: dict[str, Any] | None = None,
        outcome_records: Iterable["OutcomeRecord"] | None = None,
        execution_overhead: Any | None = None,
    ) -> "CampaignAudit":
        """Audit the current ledger against this executor's frozen plan."""
        from ..analysis.campaign_audit import audit_campaign
        from ..analysis.claims import ClaimType
        from ..analysis.overhead import load_execution_overhead

        if claim_type is None:
            claim_type = ClaimType.SINGLE_RUN_OUTCOME
        if outcome_records is None and (self.output / "outcomes.jsonl").is_file():
            outcome_records = self.outcome_ledger().records
        evidence_issues = list(self._audit_evidence_issues())
        if execution_overhead is None:
            overhead_path = self.output / "execution-overhead.json"
            if overhead_path.is_file():
                try:
                    execution_overhead = load_execution_overhead(overhead_path)
                except (OSError, ValueError, TypeError) as exc:
                    evidence_issues.append(f"execution overhead is invalid: {exc}")
        claim_evidence = dict(evidence or {})
        claim_evidence["trusted_artifacts"] = (
            claim_evidence.get("trusted_artifacts", True) is not False and not evidence_issues
        )
        return audit_campaign(
            self.plan,
            self.ledger.records,
            claim_type=claim_type,
            evidence=claim_evidence,
            outcome_records=outcome_records,
            evidence_issues=evidence_issues,
            execution_overhead=execution_overhead,
        )

    def _audit_evidence_issues(self) -> tuple[str, ...]:
        records = {record.get("attempt_id"): record for record in self.ledger.records}
        issues: list[str] = []
        for attempt in self.plan.attempts:
            attempt_id = attempt.key.attempt_id
            record = records.get(attempt_id)
            if record is None or record.get("status") == "cancelled":
                continue
            attempt_dir = self.output / "attempts" / attempt_id
            verification = verify_artifact_manifest(attempt_dir)
            if not verification["valid"]:
                issues.append(
                    f"{attempt_id}: artifact manifest is invalid: "
                    f"{verification.get('mismatches', ())}"
                )
                continue
            if verification.get("status") != record.get("status"):
                issues.append(
                    f"{attempt_id}: artifact manifest status does not match ledger status"
                )
            try:
                self._verify_runtime_receipt(attempt, attempt_dir)
                receipt = load_runtime_receipt(attempt_dir / "runtime-receipt.json")
                if receipt.get("status") != record.get("status"):
                    issues.append(
                        f"{attempt_id}: runtime receipt status does not match ledger status"
                    )
            except RuntimeError as exc:
                issues.append(str(exc))
        return tuple(issues)

    def outcome_ledger(self) -> Any:
        """Open the plan-bound scorer outcome ledger for this campaign."""
        from ..analysis.outcomes import OutcomeLedger

        return OutcomeLedger(
            self.output / "outcomes.jsonl",
            attempt_ids=frozenset(attempt.key.attempt_id for attempt in self.plan.attempts),
            plan_digest_sha256=self.plan.plan_digest_sha256,
        )

    def archive(self, destination: Path) -> dict[str, str | int]:
        """Write this campaign's current evidence as an immutable bundle."""
        from .archive import write_campaign_archive

        return write_campaign_archive(self.output, destination)

    def publish_artifact(self, store: Any) -> dict[str, str | int]:
        """Publish the current immutable campaign bundle through an artifact store."""
        from .artifacts import publish_campaign_archive

        return publish_campaign_archive(self.output, store).to_dict()

    def compile_counterfactual_plan(
        self,
        interventions: Iterable[Any],
        destination: Path | None = None,
    ) -> Any:
        """Freeze robustness branches against this executor's nominal plan.

        The evaluator still owns simulator state and disturbance application;
        this boundary owns source-plan lineage and optional serialization.
        """
        from .counterfactual import compile_counterfactual_plan

        counterfactual = compile_counterfactual_plan(self.plan, interventions)
        if destination is not None:
            counterfactual.write(destination)
        return counterfactual

    def run_counterfactual(
        self,
        interventions: Iterable[Any],
        evaluator: Any,
        *,
        output: Path | None = None,
    ) -> tuple[Any, ...]:
        """Run paired nominal/intervention branches with frozen lineage."""
        from .counterfactual import execute_counterfactual_plan

        counterfactual = self.compile_counterfactual_plan(interventions)
        return execute_counterfactual_plan(counterfactual, evaluator, output=output)


def _validate_execution_safety(plan: FrozenCampaignPlan) -> None:
    """Recheck hardware safety invariants at the execution boundary.

    Plans may be loaded or constructed without passing through the declarative
    compiler. Physical environments therefore need the same authorization and
    no-automatic-retry checks before a worker can instantiate an adapter.
    """
    protocol = plan.protocol or {}
    section = protocol.get("S", {})
    environments = section.get("environments", []) if isinstance(section, dict) else []
    if not isinstance(environments, list):
        raise ValueError("frozen plan environment declarations must be a list")
    referenced_environment_ids = {attempt.key.environment_id for attempt in plan.attempts}
    for index, environment in enumerate(environments):
        if not isinstance(environment, dict):
            raise ValueError(f"frozen plan environment {index} must be a mapping")
        if environment.get("kind") != "physical":
            continue
        enabled = environment.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError(
                f"physical environment {environment.get('id', index)} enabled must be boolean"
            )
        environment_id = environment.get("id", index)
        if environment_id in referenced_environment_ids and "enabled" not in environment:
            raise ValueError(f"physical environment {environment_id} must be explicitly enabled")
        if environment_id in referenced_environment_ids and enabled is not True:
            raise ValueError(
                f"physical environment {environment_id} is referenced by the frozen plan "
                "but is not enabled"
            )
        if not enabled:
            continue
        if environment.get("requires_authorization") is not True:
            raise ValueError(
                f"physical environment {environment_id} requires explicit authorization"
            )
        if environment.get("retry_policy", "none") != "none" or environment.get(
            "auto_retry", False
        ):
            raise ValueError(
                f"physical environment {environment_id} must disable automatic retries"
            )


def _validate_worldepisode_protocol(plan: FrozenCampaignPlan) -> None:
    """Apply the frozen WorldEpisode contract before any attempt is scheduled."""
    protocol = plan.protocol or {}
    binding = protocol.get("worldepisode")
    if binding is None:
        return
    if not isinstance(binding, dict):
        raise ValueError("frozen plan worldepisode binding must be a mapping")
    record = binding.get("record")
    if not isinstance(record, dict):
        raise ValueError("frozen plan worldepisode binding requires a record mapping")
    from ..integrations.worldepisode import preflight_worldepisode

    result = preflight_worldepisode(
        record,
        require_reference=binding.get("require_reference", False) is True,
        strict=binding.get("strict", False) is True,
        expected_episode_id=binding.get("expected_episode_id"),
        expected_revision_id=binding.get("expected_revision_id"),
    )
    if not result.valid:
        raise ValueError(
            "frozen plan WorldEpisode preflight failed: "
            + "; ".join(str(item.get("message", item)) for item in result.diagnostics)
        )


def _resource_budget(plan: FrozenCampaignPlan) -> ResourceBudget | None:
    evaluation = (plan.protocol or {}).get("P", {}).get("evaluation", {})
    values = evaluation.get("resource_budget", {})
    if not isinstance(values, dict):
        return None
    if not any(
        name in values
        for name in (
            "max_policy_calls",
            "max_wall_time_ms",
            "max_compute_time_ms",
            "max_gpu_hours",
            "max_bytes",
            "max_policy_queries",
            "retry_limit",
            "per_cell_timeout_seconds",
        )
    ):
        return None
    return ResourceBudget(
        max_inference_calls=values.get("max_policy_calls"),
        max_wall_time_ms=values.get("max_wall_time_ms"),
        max_compute_time_ms=values.get("max_compute_time_ms"),
        max_gpu_hours=values.get("max_gpu_hours"),
        max_bytes=values.get("max_bytes"),
        max_policy_queries=values.get("max_policy_queries"),
        retry_limit=values.get("retry_limit"),
        per_cell_timeout_seconds=values.get("per_cell_timeout_seconds"),
    )


def _execution_strategy(plan: FrozenCampaignPlan) -> str:
    evaluation = (plan.protocol or {}).get("P", {}).get("evaluation", {})
    return evaluation.get("execution_strategy", "sync")


def _max_cache_entries(plan: FrozenCampaignPlan) -> int:
    evaluation = (plan.protocol or {}).get("P", {}).get("evaluation", {})
    return evaluation.get("max_cache_entries", 256)


def _calibration(plan: FrozenCampaignPlan, environment_id: str) -> dict[str, Any] | None:
    environments = (plan.protocol or {}).get("S", {}).get("environments", [])
    for environment in environments:
        if isinstance(environment, dict) and environment.get("id") == environment_id:
            value = environment.get("calibration")
            return dict(value) if isinstance(value, dict) else None
    return None


def _benchmark_validity(plan: FrozenCampaignPlan) -> dict[str, Any] | None:
    evaluation = (plan.protocol or {}).get("P", {}).get("evaluation", {})
    value = evaluation.get("validity")
    return dict(value) if isinstance(value, dict) else None


def _model_reference(plan: FrozenCampaignPlan) -> dict[str, Any] | None:
    model = (plan.protocol or {}).get("M", {})
    if not isinstance(model, dict) or not model:
        return None
    allowed = ("adapter", "architecture", "checkpoint", "robot_profile")
    return {name: model[name] for name in allowed if name in model}
