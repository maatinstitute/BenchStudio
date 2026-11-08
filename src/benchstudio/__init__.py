"""Public research evaluation API. Native inference configuration stays caller-owned."""
from .system_pipeline import System, Benchmark, Score
from .evaluation_engine import EvaluationConfig, EvaluationEngine, EvaluationCheck
from .pipeline import pipeline
from .system_evidence import open_run
from .episodes import ActionBatch, EpisodeCoverage, EpisodeIsolation, EpisodeOutcome, EpisodeRecord
from .results import EvaluationReport, inspect_result

__version__ = "0.1.0rc1"

__all__ = [
    "System", "Benchmark", "Score", "EvaluationConfig", "EvaluationEngine",
    "EvaluationCheck", "pipeline", "open_run", "EvaluationReport", "inspect_result",
    "ActionBatch", "EpisodeCoverage", "EpisodeIsolation", "EpisodeOutcome", "EpisodeRecord",
]


def __getattr__(name):
    # Preserve explicit old imports without loading every subsystem on import bs.
    # Import machinery may request submodule names; only resolve known exports.
    if name.startswith("_"):
        raise AttributeError(name)
    from importlib import import_module
    legacy = import_module(".compat", __name__)
    if name in legacy.__all__:
        return getattr(legacy, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(__all__) | {"__version__"})
