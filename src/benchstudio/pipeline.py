"""Task-oriented public pipelines for common offline BenchStudio workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .analysis import CampaignAudit, ClaimType, audit_campaign_directory


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


def pipeline(task: str, **kwargs: Any) -> CampaignAuditPipeline:
    """Create a task-oriented BenchStudio pipeline.

    The first supported task, campaign-audit, audits an existing directory
    offline. It does not launch a simulator, policy runtime, or model.
    """
    if task != "campaign-audit":
        raise ValueError(
            f"unsupported BenchStudio pipeline task {task!r}; "
            "supported task: 'campaign-audit'"
        )
    return CampaignAuditPipeline(**kwargs)
