"""BenchStudio temporal-fidelity evaluation core."""

from .contracts import ActionChunk, Observation, Policy, Simulator
from .compare import build_comparison_report
from .adapters import AdapterDescriptor, AdapterRegistry, Dependency, default_registry
from .evidence import NdjsonWriter, environment_fingerprint
from .replay import ReplayPolicy, ReplaySimulator, load_joint_sequence
from .trajectory import compare_trajectories, load_trajectory
from .runner import EpisodeResult, RunConfig, run_episodes

__all__ = [
    "ActionChunk",
    "AdapterDescriptor",
    "AdapterRegistry",
    "Dependency",
    "NdjsonWriter",
    "EpisodeResult",
    "Observation",
    "Policy",
    "RunConfig",
    "Simulator",
    "ReplayPolicy",
    "ReplaySimulator",
    "build_comparison_report",
    "default_registry",
    "environment_fingerprint",
    "load_joint_sequence",
    "compare_trajectories",
    "load_trajectory",
    "run_episodes",
]
