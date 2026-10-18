"""Frozen campaign planning and append-only attempt accounting."""

from .archive import (
    CampaignArchiveError,
    build_campaign_archive,
    campaign_archive_digest,
    extract_verified_campaign_archive,
    write_campaign_archive,
)
from .artifacts import (
    ArtifactReference,
    ArtifactStore,
    LocalArtifactStore,
    publish_campaign_archive,
)
from .confirmation import (
    ConfirmationCase,
    ConfirmationCaseResult,
    ConfirmationEvaluation,
    FrozenConfirmationPlan,
    SearchCandidate,
    compile_confirmation_plan,
    execute_confirmation_plan,
    validate_confirmation_plan,
)
from .counterfactual import (
    CounterfactualCell,
    CounterfactualPair,
    FrozenCounterfactualPlan,
    Intervention,
    compile_counterfactual_plan,
    validate_counterfactual_pair,
    validate_counterfactual_plan,
)
from .executor import CampaignExecutionSummary, CampaignExecutor
from .frozen_plan import AttemptKey, CampaignPlanner, FrozenCampaignPlan, PlannedAttempt
from .io import load_campaign_document
from .ledger import AttemptLedger
from .paired_design import compile_balanced_paired_plan
from .search import (
    FrozenSearchPlan,
    MinimizedCounterexample,
    PerturbationDimension,
    SearchCase,
    SearchCaseResult,
    SearchEvaluation,
    build_search_candidates,
    compile_search_plan,
    execute_search_plan,
    minimize_counterexample,
    validate_search_plan,
)
from .spec import compile_campaign_spec
from .worker import WorkerLease, WorkerLeaseManager

__all__ = [
    "AttemptKey",
    "CampaignArchiveError",
    "AttemptLedger",
    "WorkerLease",
    "WorkerLeaseManager",
    "compile_balanced_paired_plan",
    "CampaignPlanner",
    "CampaignExecutionSummary",
    "CampaignExecutor",
    "build_campaign_archive",
    "campaign_archive_digest",
    "extract_verified_campaign_archive",
    "write_campaign_archive",
    "ArtifactReference",
    "ArtifactStore",
    "LocalArtifactStore",
    "publish_campaign_archive",
    "load_campaign_document",
    "compile_campaign_spec",
    "CounterfactualCell",
    "CounterfactualPair",
    "FrozenCounterfactualPlan",
    "compile_counterfactual_plan",
    "ConfirmationCase",
    "ConfirmationCaseResult",
    "ConfirmationEvaluation",
    "FrozenConfirmationPlan",
    "SearchCandidate",
    "compile_confirmation_plan",
    "execute_confirmation_plan",
    "validate_confirmation_plan",
    "FrozenCampaignPlan",
    "Intervention",
    "PlannedAttempt",
    "validate_counterfactual_pair",
    "validate_counterfactual_plan",
    "PerturbationDimension",
    "SearchCase",
    "SearchCaseResult",
    "SearchEvaluation",
    "FrozenSearchPlan",
    "MinimizedCounterexample",
    "build_search_candidates",
    "compile_search_plan",
    "execute_search_plan",
    "minimize_counterexample",
    "validate_search_plan",
]
