"""BenchStudio temporal-fidelity evaluation core."""

from .adapters import AdapterDescriptor, AdapterRegistry, Dependency, default_registry
from .compare import build_comparison_report
from .contracts import ActionChunk, Observation, ObservationFrame, Policy, Simulator, Timestamp
from .evidence import (
    NdjsonWriter,
    build_artifact_manifest,
    environment_fingerprint,
    verify_artifact_manifest,
)
from .replay import ReplayPolicy, ReplaySimulator, load_joint_sequence
from .runner import EpisodeResult, RunConfig, run_episodes
from .trajectory import compare_trajectories, load_trajectory

__all__ = [
    "ActionChunk",
    "AdapterDescriptor",
    "AdapterRegistry",
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
    "build_comparison_report",
    "default_registry",
    "environment_fingerprint",
    "build_artifact_manifest",
    "verify_artifact_manifest",
    "load_joint_sequence",
    "compare_trajectories",
    "load_trajectory",
    "run_episodes",
]
