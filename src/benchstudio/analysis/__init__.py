"""Offline validity and uncertainty analyses."""

from .acceptance import (
    AcceptanceCheck,
    EvaluationAcceptanceReport,
    audit_evaluation_acceptance,
)
from .agreement import DIMENSIONS, LABELS
from .agreement import compare as compare_annotation_packets
from .agreement import metrics as annotation_agreement_metrics
from .agreement import validate as validate_annotation_packet
from .campaign_audit import CampaignAudit, audit_campaign, audit_campaign_directory
from .claims import ClaimDecision, ClaimType, validate_claim
from .dataset_manifest import DatasetResolution, resolve_manifest
from .development_receipts import (
    build_development_receipt,
    read_development_receipt,
    validate_development_receipt,
    write_development_receipt,
)
from .failure_events import EventBookmark, bookmark_critical_events
from .inference_schedule import InferenceEvent, InferenceScheduleAudit, audit_inference_schedule
from .ledger_validation import compare as compare_refinement_ledgers
from .ledger_validation import validate as validate_refinement_ledger
from .ledger_validation import validate_completed as validate_completed_refinement_ledger
from .metadata_conditioning import (
    SCHEMA_VERSION as OUTCOME_METADATA_SCHEMA_VERSION,
)
from .metadata_conditioning import (
    condition_prompt,
    format_metadata,
    prompt_mode_metadata,
    validate_metadata,
)
from .missingness import MissingOutcomeBounds, missing_outcome_bounds, robopad_paired_bounds
from .observation_age_audit import analyze as analyze_observation_age
from .observation_age_audit import validate_inputs as validate_observation_age_inputs
from .outcome_eval import (
    boundary_outcome,
    first_attainment_step,
    inference_kwargs,
    prompt_mode_for_arm,
    validate_evaluation_branch,
    validate_replay_attainment,
)
from .outcome_report import (
    analyze_primary,
    clopper_pearson,
    summarize_cells,
)
from .outcome_report import (
    discordance_interval as outcome_discordance_interval,
)
from .outcomes import (
    OutcomeLedger,
    OutcomeProvenanceAudit,
    OutcomeRecord,
    audit_outcome_provenance,
    validate_outcome_record,
)
from .overhead import (
    ExecutionOverhead,
    TimingProvenance,
    audit_execution_overhead,
    load_execution_overhead,
    write_execution_overhead,
)
from .paired import (
    PairedOutcomeSummary,
    clopper_pearson_interval,
    discordance_interval,
    summarize_paired_outcomes,
)
from .parity import (
    ObservationParityReport,
    PolicyParityReport,
    compare_observation_streams,
    compare_policy_outputs,
    compare_policy_trace_files,
    write_parity_report,
)
from .recovery import (
    CounterfactualOutcomeAudit,
    RecoverySummary,
    audit_counterfactual_outcomes,
    load_recovery_records,
    summarize_recovery_outcomes,
    write_recovery_report,
)
from .refinement_protocol import (
    ATOL,
    CONDITIONS,
    RTOL,
    array_record,
    batch_one_success,
    compare_arrays,
    development_schedule,
    image_variants,
    json_line,
    keyed_seed,
    observation_field_shas,
    observation_sha,
    parity_report,
    profiler_counts,
    require,
    select_schedule,
    sha,
)
from .resources import (
    ResourceAudit,
    ResourceBudget,
    ResourcePoint,
    audit_resources,
    pareto_frontier,
)
from .responsiveness import score as score_selective_responsiveness
from .responsiveness import split_for as responsiveness_split_for
from .responsiveness import summarize as summarize_selective_responsiveness
from .responsiveness import validate as validate_selective_responsiveness
from .result_metrics import completed_outcomes
from .result_metrics import summarize as summarize_refinement_results
from .robopad_exposure import LIMITATIONS, audit_splits, build_inventory, demo_family, family_id
from .robopad_visual_balance import image_distance, match_candidates
from .score_coverage import ScoreCoverage, audit_score_coverage
from .transfer import (
    TransferFidelityReport,
    TransferGap,
    estimate_transfer_gap,
    load_transfer_records,
    summarize_transfer_fidelity,
    write_transfer_fidelity_report,
)

__all__ = [
    "MissingOutcomeBounds",
    "ExecutionOverhead",
    "TimingProvenance",
    "OutcomeRecord",
    "OutcomeLedger",
    "OutcomeProvenanceAudit",
    "audit_outcome_provenance",
    "validate_outcome_record",
    "audit_execution_overhead",
    "load_execution_overhead",
    "write_execution_overhead",
    "analyze_primary",
    "clopper_pearson",
    "outcome_discordance_interval",
    "summarize_cells",
    "prompt_mode_for_arm",
    "inference_kwargs",
    "boundary_outcome",
    "first_attainment_step",
    "validate_replay_attainment",
    "validate_evaluation_branch",
    "analyze_observation_age",
    "validate_observation_age_inputs",
    "CONDITIONS",
    "RTOL",
    "ATOL",
    "array_record",
    "batch_one_success",
    "compare_arrays",
    "development_schedule",
    "json_line",
    "keyed_seed",
    "observation_field_shas",
    "observation_sha",
    "parity_report",
    "image_variants",
    "profiler_counts",
    "require",
    "select_schedule",
    "sha",
    "EventBookmark",
    "InferenceEvent",
    "InferenceScheduleAudit",
    "audit_inference_schedule",
    "ClaimDecision",
    "AcceptanceCheck",
    "EvaluationAcceptanceReport",
    "audit_evaluation_acceptance",
    "DIMENSIONS",
    "LABELS",
    "compare_annotation_packets",
    "annotation_agreement_metrics",
    "validate_annotation_packet",
    "CampaignAudit",
    "audit_campaign",
    "audit_campaign_directory",
    "ClaimType",
    "build_development_receipt",
    "read_development_receipt",
    "validate_development_receipt",
    "write_development_receipt",
    "DatasetResolution",
    "resolve_manifest",
    "ScoreCoverage",
    "audit_score_coverage",
    "bookmark_critical_events",
    "audit_resources",
    "estimate_transfer_gap",
    "missing_outcome_bounds",
    "robopad_paired_bounds",
    "LIMITATIONS",
    "audit_splits",
    "build_inventory",
    "demo_family",
    "family_id",
    "image_distance",
    "match_candidates",
    "ResourceAudit",
    "ResourceBudget",
    "ResourcePoint",
    "pareto_frontier",
    "RecoverySummary",
    "CounterfactualOutcomeAudit",
    "audit_counterfactual_outcomes",
    "summarize_recovery_outcomes",
    "load_recovery_records",
    "write_recovery_report",
    "TransferGap",
    "TransferFidelityReport",
    "summarize_transfer_fidelity",
    "load_transfer_records",
    "write_transfer_fidelity_report",
    "PolicyParityReport",
    "ObservationParityReport",
    "PairedOutcomeSummary",
    "clopper_pearson_interval",
    "discordance_interval",
    "summarize_paired_outcomes",
    "compare_policy_outputs",
    "compare_policy_trace_files",
    "compare_observation_streams",
    "write_parity_report",
    "validate_claim",
    "score_selective_responsiveness",
    "summarize_selective_responsiveness",
    "validate_selective_responsiveness",
    "responsiveness_split_for",
    "completed_outcomes",
    "summarize_refinement_results",
    "validate_refinement_ledger",
    "validate_completed_refinement_ledger",
    "OUTCOME_METADATA_SCHEMA_VERSION",
    "condition_prompt",
    "format_metadata",
    "prompt_mode_metadata",
    "validate_metadata",
    "compare_refinement_ledgers",
]
