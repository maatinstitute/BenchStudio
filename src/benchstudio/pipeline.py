"""Task-oriented public pipelines for campaign execution and audit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .analysis import CampaignAudit, ClaimType, audit_campaign_directory
from .campaigns import CampaignExecutionSummary, CampaignExecutor, compile_campaign_spec
from .campaigns.io import load_campaign_document


@dataclass(frozen=True)
class CampaignRun:
    """Execution receipt paths and counts for one frozen campaign."""

    output_dir: Path
    plan_path: Path
    execution: CampaignExecutionSummary

    def summary(self) -> str:
        """Return a compact execution summary without making a scientific claim."""
        return (
            f"Campaign {self.execution.run_id}: "
            f"{len(self.execution.committed_attempt_ids)} completed, "
            f"{len(self.execution.failed_attempt_ids)} failed, "
            f"{len(self.execution.missing_attempt_ids)} missing, "
            f"{len(self.execution.skipped_attempt_ids)} already recorded."
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible execution accounting and artifact locations."""
        return {
            "schema": "benchstudio_campaign_run_v1",
            "run_id": self.execution.run_id,
            "plan_digest_sha256": self.execution.plan_digest_sha256,
            "output_dir": str(self.output_dir),
            "plan_path": str(self.plan_path),
            "committed_attempt_ids": list(self.execution.committed_attempt_ids),
            "failed_attempt_ids": list(self.execution.failed_attempt_ids),
            "skipped_attempt_ids": list(self.execution.skipped_attempt_ids),
            "missing_attempt_ids": list(self.execution.missing_attempt_ids),
            "leased_out_attempt_ids": list(self.execution.leased_out_attempt_ids),
            "cancelled_attempt_ids": list(self.execution.cancelled_attempt_ids),
        }

    def analyze(
        self,
        *,
        claim_type: ClaimType | str = ClaimType.SINGLE_RUN_OUTCOME,
        evidence: dict[str, Any] | None = None,
    ) -> CampaignAudit:
        """Explicitly audit persisted evidence after execution."""
        return audit_campaign_directory(
            self.output_dir,
            claim_type=ClaimType(claim_type),
            evidence=evidence,
        )


class CampaignEvaluationPipeline:
    """Execute a declared campaign through explicit mock or installed adapters.

    A campaign can be supplied as JSON/YAML or as familiar task/model/
    environment inputs. Calling run() is the explicit execution step;
    construction does not load a model or contact an environment.
    """

    def __init__(
        self,
        campaign: str | Path | Mapping[str, Any] | None = None,
        *,
        output_dir: str | Path,
        execution: str = "registry",
        workers: int = 1,
        task: str | Mapping[str, Any] | None = None,
        task_revision: str | None = None,
        model: str | Mapping[str, Any] | None = None,
        environment: str | Mapping[str, Any] | None = None,
        seeds: list[int] | tuple[int, ...] | None = None,
        conditions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
        run_id: str | None = None,
        benchmark: str | None = None,
    ) -> None:
        if execution not in {"registry", "mock"}:
            raise ValueError("execution must be 'registry' or 'mock'")
        if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
            raise ValueError("workers must be a positive integer")
        direct_values = (task, model, environment, seeds, conditions, run_id, benchmark)
        if campaign is not None and any(value is not None for value in direct_values):
            raise ValueError("campaign cannot be combined with direct task/model/environment inputs")
        if campaign is None and not all(
            value is not None for value in (task, model, environment, seeds, conditions, run_id)
        ):
            raise ValueError(
                "provide campaign or all of task, model, environment, seeds, conditions, and run_id"
            )
        self.campaign = campaign
        self.direct_values = {
            "task": task,
            "task_revision": task_revision,
            "model": model,
            "environment": environment,
            "seeds": seeds,
            "conditions": conditions,
            "run_id": run_id,
            "benchmark": benchmark,
        }
        self.output_dir = Path(output_dir)
        self.execution = execution
        self.workers = workers

    def __call__(self) -> CampaignRun:
        """Execute the configured frozen campaign."""
        return self.run()

    def run(self) -> CampaignRun:
        """Compile, freeze, and execute the declared campaign."""
        if self.campaign is not None:
            spec = (
                dict(self.campaign)
                if isinstance(self.campaign, Mapping)
                else load_campaign_document(Path(self.campaign))
            )
        else:
            spec = _campaign_from_direct_inputs(**self.direct_values)
        plan = compile_campaign_spec(spec)
        if self.execution == "mock":
            from .adapters import default_registry
            from .mock import MockPolicy, MockSimulator

            executor = CampaignExecutor(
                plan,
                self.output_dir,
                policy_factory=lambda _attempt: MockPolicy(),
                simulator_factory=lambda _attempt: MockSimulator(),
                adapter_registry=default_registry(),
            )
        else:
            model_declaration = plan.protocol.get("M", {})
            environments = plan.protocol.get("S", {}).get("environments", [])
            if not isinstance(model_declaration, dict) or not model_declaration.get("adapter"):
                raise ValueError(
                    "registry execution requires a declared model.adapter in the campaign"
                )
            missing = [
                item.get("id", "<unknown>")
                for item in environments
                if isinstance(item, dict)
                and item.get("enabled", item.get("kind") != "physical")
                and not item.get("adapter")
            ]
            if missing:
                raise ValueError(
                    "registry execution requires adapters for enabled environments: "
                    + ", ".join(missing)
                )
            from .adapters import default_registry
            from .model_adapters import default_model_registry

            executor = CampaignExecutor(
                plan,
                self.output_dir,
                adapter_registry=default_registry(),
                model_registry=default_model_registry(),
            )
        execution = (
            executor.run_parallel(self.workers) if self.workers > 1 else executor.run()
        )
        return CampaignRun(
            output_dir=self.output_dir,
            plan_path=self.output_dir / "campaign-plan.json",
            execution=execution,
        )


def _campaign_from_direct_inputs(
    *,
    task: str | Mapping[str, Any] | None,
    task_revision: str | None,
    model: str | Mapping[str, Any] | None,
    environment: str | Mapping[str, Any] | None,
    seeds: list[int] | tuple[int, ...] | None,
    conditions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    run_id: str | None,
    benchmark: str | None,
) -> dict[str, Any]:
    task_id, revision, task_benchmark = _task_identity(task, task_revision, benchmark)
    model_record = _adapter_input(model, name="model")
    environment_record = _adapter_input(environment, name="environment")
    if not isinstance(seeds, (list, tuple)) or not seeds:
        raise ValueError("seeds must be a non-empty sequence of integers")
    if any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds):
        raise ValueError("seeds must contain only integers")
    if not isinstance(conditions, (list, tuple)) or not conditions or any(
        not isinstance(condition, Mapping) for condition in conditions
    ):
        raise ValueError("conditions must be a non-empty sequence of mappings")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string")
    task_record: dict[str, Any] = {"task_id": task_id, "task_revision": revision}
    if task_benchmark is not None:
        task_record["benchmark"] = task_benchmark
    return {
        "schema": "benchstudio.campaign.v1",
        "experiment": {"name": run_id, "protocol_revision": "1"},
        "model": model_record,
        "task": task_record,
        "environments": [environment_record],
        "evaluation": {
            "seeds": list(seeds),
            "conditions": [dict(condition) for condition in conditions],
            "paired": True,
            "missing_outcomes": "preserve",
            "confirmation_plan": "frozen",
        },
    }


def _task_identity(
    task: str | Mapping[str, Any] | None,
    task_revision: str | None,
    benchmark: str | None,
) -> tuple[str, str, str | None]:
    if isinstance(task, str) and task.strip():
        task_id = task.strip()
        revision = task_revision
        task_benchmark = benchmark
    elif isinstance(task, Mapping):
        task_id = task.get("id", task.get("task_id"))
        revision = task.get("revision", task.get("task_revision", task_revision))
        task_benchmark = task.get("benchmark", benchmark)
    else:
        raise ValueError("task must be a non-empty name or a mapping with id and revision")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task requires a non-empty id")
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("task_revision is required to pin the task")
    if task_benchmark is not None and (
        not isinstance(task_benchmark, str) or not task_benchmark.strip()
    ):
        raise ValueError("benchmark must be a non-empty string")
    return task_id, revision, task_benchmark


def _adapter_input(value: str | Mapping[str, Any] | None, *, name: str) -> dict[str, Any]:
    if isinstance(value, str) and value.strip():
        declaration: dict[str, Any] = {"adapter": value.strip()}
    elif isinstance(value, Mapping):
        declaration = dict(value)
    else:
        raise ValueError(f"{name} must be an adapter name or a mapping")
    adapter = declaration.pop("adapter", None)
    if not isinstance(adapter, str) or not adapter.strip():
        raise ValueError(f"{name}.adapter must be a non-empty string")
    if "config" in declaration and "adapter_config" in declaration:
        raise ValueError(f"{name} accepts config or adapter_config, not both")
    config = (
        declaration.pop("config")
        if "config" in declaration
        else declaration.pop("adapter_config", {})
    )
    if not isinstance(config, Mapping):
        raise ValueError(f"{name}.config must be a mapping")
    if name == "model":
        record = {"adapter": adapter.strip(), "architecture": declaration.pop("architecture", adapter)}
        if "checkpoint" in declaration:
            record["checkpoint"] = declaration.pop("checkpoint")
        if "capabilities" in declaration:
            record["capabilities"] = declaration.pop("capabilities")
        record["adapter_config"] = dict(config)
    else:
        environment_id = declaration.pop("id", f"{adapter.strip()}-0")
        kind = declaration.pop("kind", "simulator")
        record = {
            "id": environment_id,
            "kind": kind,
            "adapter": adapter.strip(),
            "adapter_config": dict(config),
        }
        if "enabled" in declaration:
            record["enabled"] = declaration.pop("enabled")
        if "required_capabilities" in declaration:
            record["required_capabilities"] = declaration.pop("required_capabilities")
    if declaration:
        raise ValueError(f"unsupported {name} fields: {', '.join(sorted(declaration))}")
    return record


class CampaignAuditPipeline:
    """Audit an existing campaign directory without loading adapters or executing it."""

    def __init__(
        self, *, claim_type: ClaimType | str = ClaimType.SINGLE_RUN_OUTCOME
    ) -> None:
        self.claim_type = ClaimType(claim_type)

    def __call__(self, source: str | Path) -> CampaignAudit:
        """Audit a saved campaign directory and return its structured report."""
        return self.run(source)

    def run(self, source: str | Path) -> CampaignAudit:
        """Run the offline audit. This does not construct a policy or simulator."""
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"campaign directory does not exist: {path}")
        if not path.is_dir():
            raise ValueError(
                "campaign-audit expects a campaign directory; "
                "verify an archive with verify_campaign_archive instead"
            )
        return audit_campaign_directory(path, claim_type=self.claim_type)


def pipeline(name: str = "evaluate", **kwargs: Any) -> Any:
    """Create a task-oriented BenchStudio pipeline.

    The default task is evaluate. system-evaluation is a compatibility alias.\n    Other tasks are ablation, replay, robotics-evaluation and campaign-audit. Evaluation
    accepts a campaign file or explicit task/model/environment inputs. It
    never infers a model, simulator, or scoring function.
    """
    if name == "ablation":
        from .experimental import AblationStudy
        return AblationStudy(**kwargs)
    if name == "replay":
        from .replay_pipeline import ReplayPipeline
        if "source" not in kwargs:
            raise ValueError("replay requires source=archive_path")
        source = kwargs.pop("source")
        return ReplayPipeline.from_archive(source, **kwargs)
    if name in ("evaluate", "system-evaluation"):
        from .system_pipeline import SystemEvaluationPipeline
        return SystemEvaluationPipeline(**kwargs)
    if name == "campaign-audit":
        return CampaignAuditPipeline(**kwargs)
    if name == "robotics-evaluation":
        return CampaignEvaluationPipeline(**kwargs)
    raise ValueError(
        f"unsupported BenchStudio pipeline task {name!r}; "
        "supported tasks: 'evaluate', 'ablation', 'replay', 'system-evaluation', 'robotics-evaluation', 'campaign-audit'"
    )

