"""Frozen campaign planning and append-only attempt accounting."""

from .counterfactual import CounterfactualCell, Intervention, validate_counterfactual_pair
from .executor import CampaignExecutionSummary, CampaignExecutor
from .frozen_plan import AttemptKey, CampaignPlanner, FrozenCampaignPlan, PlannedAttempt
from .ledger import AttemptLedger
from .paired_design import compile_balanced_paired_plan
from .spec import compile_campaign_spec
from .worker import WorkerLease, WorkerLeaseManager

__all__ = [
    "AttemptKey",
    "AttemptLedger",
    "WorkerLease",
    "WorkerLeaseManager",
    "compile_balanced_paired_plan",
    "CampaignPlanner",
    "CampaignExecutionSummary",
    "CampaignExecutor",
    "compile_campaign_spec",
    "CounterfactualCell",
    "FrozenCampaignPlan",
    "Intervention",
    "PlannedAttempt",
    "validate_counterfactual_pair",
]
