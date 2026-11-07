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
    """Execute a declared campaign using mock fixtures or installed adapters.

    Constructing the pipeline only validates its options. Calling run() or the
    pipeline itself is the explicit execution step. The campaign document
    freezes task, model, environment, schedule, and runtime configuration.
    Analysis is a separate call on the returned CampaignRun.
    """

    def __init__(
        self,
        campaign: str | Path | Mapping[str, Any],
        output_dir: str | Path,
        *,
        execution: str = "registry",
        workers: int = 1,
    ) -> None:
        if execution not in {"registry", "mock"}:
            raise ValueError("execution must be 'registry' or 'mock'")
        if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
            raise ValueError("workers must be a positive integer")
        self.campaign = campaign
        self.output_dir = Path(output_dir)
        self.execution = execution
        self.workers = workers

    def __call__(self) -> CampaignRun:
        """Execute the configured frozen campaign."""
        return self.run()

    def run(self) -> CampaignRun:
        """Compile, freeze, and execute the declared campaign."""
        spec = (
            dict(self.campaign)
            if isinstance(self.campaign, Mapping)
            else load_campaign_document(Path(self.campaign))
        )
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
            model = plan.protocol.get("M", {})
            environments = plan.protocol.get("S", {}).get("environments", [])
            if not isinstance(model, dict) or not model.get("adapter"):
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


def pipeline(task: str, **kwargs: Any) -> CampaignAuditPipeline | CampaignEvaluationPipeline:
    """Create a task-oriented BenchStudio pipeline.

    Supported tasks are robotics-evaluation and campaign-audit. Evaluation
    executes a campaign declared in a mapping or JSON/YAML file; it never
    infers a model, simulator, or scoring function.
    """
    if task == "campaign-audit":
        return CampaignAuditPipeline(**kwargs)
    if task == "robotics-evaluation":
        return CampaignEvaluationPipeline(**kwargs)
    raise ValueError(
        f"unsupported BenchStudio pipeline task {task!r}; "
        "supported tasks: 'robotics-evaluation', 'campaign-audit'"
    )
