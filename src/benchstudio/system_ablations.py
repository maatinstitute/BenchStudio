"""Controlled system-ablation declarations and trial-coverage audits.

Structural isolation checks do not, by themselves, establish a causal effect.
"""
from __future__ import annotations

from dataclasses import dataclass

from .system_comparison import SystemComparison
from .system_evidence import SystemRun, TrialKey
from .system_spec import SystemSpec


@dataclass(frozen=True)
class AblationAudit:
    structurally_isolated: bool
    changed_components: tuple[str, ...]
    added_components: tuple[str, ...]
    removed_components: tuple[str, ...]
    wiring_changed: bool
    metadata_changed: bool
    issues: tuple[str, ...]
    claim: str = "DECLARED_STRUCTURAL_ISOLATION_ONLY"


def audit_ablation(
    baseline: SystemSpec,
    candidate: SystemSpec,
    *,
    allowed_components: tuple[str, ...],
    allow_wiring_change: bool = False,
) -> AblationAudit:
    """Check whether *declared* differences are confined to selected nodes."""
    if len(allowed_components) != len(set(allowed_components)) or not allowed_components:
        raise ValueError("allowed_components must name unique nonempty nodes")
    before = {n.component_id: n for n in baseline.components}
    after = {n.component_id: n for n in candidate.components}
    added = tuple(sorted(set(after) - set(before)))
    removed = tuple(sorted(set(before) - set(after)))
    changed = tuple(sorted(
        cid for cid in set(before) & set(after) if before[cid] != after[cid]
    ))
    wiring = set(baseline.connections) != set(candidate.connections)
    metadata = dict(baseline.metadata) != dict(candidate.metadata)
    issues = []
    observed = set(changed + added + removed)
    if not observed and not wiring and not metadata:
        issues.append("no declared intervention")
    if observed - set(allowed_components):
        issues.append("unapproved component change")
    if (added or removed) and not allow_wiring_change:
        issues.append("component added or removed")
    if wiring and not allow_wiring_change:
        issues.append("wiring changed")
    if metadata:
        issues.append("system metadata changed: review possible confounders")
    return AblationAudit(
        structurally_isolated=not issues,
        changed_components=changed, added_components=added,
        removed_components=removed, wiring_changed=wiring,
        metadata_changed=metadata, issues=tuple(issues),
    )


@dataclass(frozen=True)
class TrialCoverageAudit:
    expected: int
    observed: int
    valid_outcomes: int
    missing_keys: tuple[TrialKey, ...]
    extra_keys: tuple[TrialKey, ...]
    incomplete_keys: tuple[TrialKey, ...]
    complete: bool
    claim: str = "EVIDENCE_COVERAGE_NOT_STATISTICAL_POWER"


def audit_trial_coverage(
    run: SystemRun, expected_keys: set[TrialKey] | frozenset[TrialKey]
) -> TrialCoverageAudit:
    """Check explicit scheduled units without constructing new rollouts."""
    if not isinstance(expected_keys, (set, frozenset)):
        raise TypeError("expected_keys must be a set of declared TrialKeys")
    actual = {trial.key: trial for trial in run.trials}
    planned = set(expected_keys)
    missing = tuple(sorted(planned - set(actual), key=repr))
    extra = tuple(sorted(set(actual) - planned, key=repr))
    invalid = tuple(sorted((
        key for key in planned & set(actual) if not actual[key].valid_success
    ), key=repr))
    return TrialCoverageAudit(
        expected=len(planned), observed=len(actual),
        valid_outcomes=sum(actual[key].valid_success for key in planned & set(actual)),
        missing_keys=missing, extra_keys=extra, incomplete_keys=invalid,
        complete=not (missing or extra or invalid),
    )


@dataclass(frozen=True)
class EvidenceReadiness:
    status: str
    matched_trials: int
    required_trials: int
    issues: tuple[str, ...]


def review_ablation_evidence(
    isolation: AblationAudit,
    comparison: SystemComparison,
    *,
    min_matched_pairs: int,
) -> EvidenceReadiness:
    """Decide if declared design/evidence prerequisites pass, not causality."""
    if type(min_matched_pairs) is not int or min_matched_pairs < 1:
        raise ValueError("min_matched_pairs must be a positive integer")
    issues = list(isolation.issues)
    if comparison.valid_binary_pairs < min_matched_pairs:
        issues.append("insufficient valid matched outcomes for declared count target")
    if comparison.incomplete_pairs or comparison.unmatched_a or comparison.unmatched_b:
        issues.append("incomplete or unmatched evidence")
    return EvidenceReadiness(
        status="DECLARED_PREREQUISITES_MET" if not issues else "INCONCLUSIVE",
        matched_trials=comparison.valid_binary_pairs,
        required_trials=min_matched_pairs,
        issues=tuple(issues),
    )
