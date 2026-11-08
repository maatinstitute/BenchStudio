"""Read-only inspection shared by offline and native results."""
from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType

from .episodes import EpisodeCoverage, EpisodeRecord
from .system_evidence import SystemRun


@dataclass(frozen=True)
class EvaluationReport:
    native: object
    coverage: EpisodeCoverage | None
    episodes: tuple[EpisodeRecord, ...]
    metrics: Mapping
    source: str

    @property
    def traces(self):
        return MappingProxyType({e.case_id: e.batches for e in self.episodes})

    @property
    def outcomes(self):
        return MappingProxyType({e.case_id: e.outcome for e in self.episodes})

    def summary(self):
        summary = getattr(self.native, "summary", None)
        text = summary() if callable(summary) else type(self.native).__name__
        coverage = "unknown" if self.coverage is None else (
            f"{len(self.coverage.observed)}/{len(self.coverage.planned)} records; "
            f"{len(self.coverage.missing)} missing")
        return f"{text}\nEvidence coverage: {coverage} ({self.source})."


def inspect_result(result, *, planned=None, episodes=()):
    """Inspect, without execution or guessed native success/coverage semantics.

    Native formats with no common records retain unknown common coverage.
    Use pipeline.report() to include its frozen episode calendar automatically.
    """
    episodes = tuple(episodes)
    if any(not isinstance(e, EpisodeRecord) for e in episodes):
        raise TypeError("episodes must contain EpisodeRecord")
    if len({e.case_id for e in episodes}) != len(episodes):
        raise ValueError("duplicate episode identity")
    metrics = {}
    if isinstance(result, SystemRun):
        if episodes or planned is not None:
            raise ValueError("offline coverage comes from its retained trials")
        ids = tuple(t.trial_id for t in result.trials)
        coverage = EpisodeCoverage(ids, tuple(t.trial_id for t in result.trials
                                               if t.status not in ("missing", "cancelled")))
        metrics = {t.trial_id: MappingProxyType(dict(t.metrics)) for t in result.trials}
        source = "offline trials"
    else:
        coverage = None if planned is None else EpisodeCoverage(
            tuple(planned), tuple(e.case_id for e in episodes))
        native_metrics = getattr(result, "metrics", None)
        if isinstance(native_metrics, Mapping):
            metrics = dict(native_metrics)  # Preserve native units/grouping; no pooling.
        source = "common episode records" if planned is not None else "native; unspecified coverage"
    return EvaluationReport(result, coverage, episodes, MappingProxyType(metrics), source)
