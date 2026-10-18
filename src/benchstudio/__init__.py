"""BenchStudio temporal-fidelity evaluation core."""

from .adapters import AdapterDescriptor, AdapterRegistry, Dependency, default_registry
from .analysis import (
    MissingOutcomeBounds,
    ScoreCoverage,
    audit_score_coverage,
    missing_outcome_bounds,
)
from .campaigns import AttemptKey, AttemptLedger, CampaignPlanner, FrozenCampaignPlan
from .compare import build_comparison_report
from .conformance import (
    ActionSpec,
    AdapterCapabilities,
    ScenarioContract,
    ValidationIssue,
    validate_action,
    validate_adapter_capabilities,
    validate_observation,
    validate_scenario_pair,
)
from .contracts import ActionChunk, Observation, ObservationFrame, Policy, Simulator, Timestamp
from .evidence import (
    NdjsonWriter,
    build_artifact_manifest,
    environment_fingerprint,
    verify_artifact_manifest,
    write_manifest_trust_anchor,
)
from .replay import ReplayPolicy, ReplaySimulator, load_joint_sequence
from .runner import EpisodeResult, RunConfig, run_episodes
from .trajectory import compare_trajectories, load_trajectory

__all__ = [
    "ActionChunk",
    "ActionSpec",
    "AdapterDescriptor",
    "AdapterCapabilities",
    "AdapterRegistry",
    "MissingOutcomeBounds",
    "AttemptKey",
    "AttemptLedger",
    "CampaignPlanner",
    "Dependency",
    "NdjsonWriter",
    "EpisodeResult",
    "Observation",
    "ObservationFrame",
    "Policy",
    "RunConfig",
    "Simulator",
    "Timestamp",
    "ReplayPolicy",
    "ReplaySimulator",
    "FrozenCampaignPlan",
    "ScenarioContract",
    "ScoreCoverage",
    "ValidationIssue",
    "build_comparison_report",
    "default_registry",
    "environment_fingerprint",
    "build_artifact_manifest",
    "verify_artifact_manifest",
    "write_manifest_trust_anchor",
    "load_joint_sequence",
    "compare_trajectories",
    "load_trajectory",
    "run_episodes",
    "audit_score_coverage",
    "missing_outcome_bounds",
    "validate_action",
    "validate_adapter_capabilities",
    "validate_observation",
    "validate_scenario_pair",
]
