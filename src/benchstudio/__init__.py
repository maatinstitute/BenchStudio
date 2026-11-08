"""Public research evaluation API. Native inference configuration stays caller-owned."""
from .system_pipeline import System, Benchmark, Score
from .evaluation_engine import EvaluationConfig, EvaluationEngine, EvaluationCheck
from .pipeline import pipeline
from .system_evidence import open_run
from .episodes import ActionBatch, EpisodeCoverage, EpisodeIsolation, EpisodeOutcome, EpisodeRecord
from .results import EvaluationReport, inspect_result

__version__ = "0.1.0rc2"

__all__ = [
    "System", "Benchmark", "Score", "EvaluationConfig", "EvaluationEngine",
    "EvaluationCheck", "pipeline", "open_run", "EvaluationReport", "inspect_result",
    "ActionBatch", "EpisodeCoverage", "EpisodeIsolation", "EpisodeOutcome", "EpisodeRecord",
]
