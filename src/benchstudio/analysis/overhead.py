from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TimingProvenance:
    clock_domain: str
    start_boundary: str
    end_boundary: str
    uncertainty_ms: float | None = None

    def validate(self) -> tuple[str, ...]:
        issues: list[str] = []
        if not self.clock_domain:
            issues.append("clock_domain is required")
        if not self.start_boundary:
            issues.append("start_boundary is required")
        if not self.end_boundary:
            issues.append("end_boundary is required")
        if self.uncertainty_ms is not None and (
            not math.isfinite(float(self.uncertainty_ms)) or self.uncertainty_ms < 0
        ):
            issues.append("uncertainty_ms must be finite and non-negative")
        return tuple(issues)

    def to_dict(self) -> dict[str, str | float | None]:
        return {
            "clock_domain": self.clock_domain,
            "start_boundary": self.start_boundary,
            "end_boundary": self.end_boundary,
            "uncertainty_ms": self.uncertainty_ms,
        }


@dataclass(frozen=True)
class ExecutionOverhead:
    matched_samples: int
    baseline_mean_ms: float | None
    instrumented_mean_ms: float | None
    added_mean_ms: float | None
    relative_overhead: float | None
    baseline_deadline_misses: int
    instrumented_deadline_misses: int
    valid: bool
    issues: tuple[str, ...]
    timing_provenance: TimingProvenance | None = None

    @property
    def provenance_complete(self) -> bool:
        return self.timing_provenance is not None and not self.timing_provenance.validate()

    def to_dict(self) -> dict[str, object]:
        return {
            "matched_samples": self.matched_samples,
            "baseline_mean_ms": self.baseline_mean_ms,
            "instrumented_mean_ms": self.instrumented_mean_ms,
            "added_mean_ms": self.added_mean_ms,
            "relative_overhead": self.relative_overhead,
            "baseline_deadline_misses": self.baseline_deadline_misses,
            "instrumented_deadline_misses": self.instrumented_deadline_misses,
            "valid": self.valid,
            "issues": list(self.issues),
            "provenance_complete": self.provenance_complete,
            "timing_provenance": (
                self.timing_provenance.to_dict() if self.timing_provenance is not None else None
            ),
        }


def write_execution_overhead(report: ExecutionOverhead, path: Path) -> None:
    """Persist an overhead audit as an independently inspectable artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema": "benchstudio_execution_overhead_v1", "report": report.to_dict()},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def load_execution_overhead(path: Path) -> ExecutionOverhead:
    """Load and validate a serialized overhead audit."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "benchstudio_execution_overhead_v1":
        raise ValueError("unsupported execution-overhead schema")
    values = payload.get("report")
    if not isinstance(values, dict):
        raise ValueError("execution-overhead report must be a mapping")
    provenance_value = values.get("timing_provenance")
    provenance = None
    if provenance_value is not None:
        if not isinstance(provenance_value, dict):
            raise ValueError("timing_provenance must be a mapping")
        provenance = TimingProvenance(
            str(provenance_value.get("clock_domain", "")),
            str(provenance_value.get("start_boundary", "")),
            str(provenance_value.get("end_boundary", "")),
            provenance_value.get("uncertainty_ms"),
        )
    report = ExecutionOverhead(
        int(values.get("matched_samples", 0)),
        values.get("baseline_mean_ms"),
        values.get("instrumented_mean_ms"),
        values.get("added_mean_ms"),
        values.get("relative_overhead"),
        int(values.get("baseline_deadline_misses", 0)),
        int(values.get("instrumented_deadline_misses", 0)),
        bool(values.get("valid", False)),
        tuple(str(issue) for issue in values.get("issues", [])),
        provenance,
    )
    if report.valid and not report.provenance_complete:
        raise ValueError("valid execution-overhead report lacks complete timing provenance")
    return report


def audit_execution_overhead(
    baseline_ms: list[float],
    instrumented_ms: list[float],
    *,
    deadline_ms: float | None = None,
    timing_provenance: TimingProvenance | None = None,
) -> ExecutionOverhead:
    """Compare same-unit timing samples without hiding missing or invalid data."""
    issues: list[str] = list(timing_provenance.validate()) if timing_provenance else []
    if len(baseline_ms) != len(instrumented_ms):
        return ExecutionOverhead(
            0,
            None,
            None,
            None,
            None,
            0,
            0,
            False,
            ("baseline and instrumented samples must have equal length",),
            timing_provenance,
        )
    if deadline_ms is not None and (not math.isfinite(float(deadline_ms)) or deadline_ms < 0):
        issues.append("deadline_ms must be finite and non-negative")
    for label, values in (("baseline", baseline_ms), ("instrumented", instrumented_ms)):
        for index, value in enumerate(values):
            if not math.isfinite(float(value)) or value < 0:
                issues.append(f"{label}[{index}] must be finite and non-negative")
    if issues:
        return ExecutionOverhead(
            len(baseline_ms), None, None, None, None, 0, 0, False, tuple(issues), timing_provenance
        )
    if not baseline_ms:
        return ExecutionOverhead(
            0, None, None, None, None, 0, 0, False, ("no timing samples",), timing_provenance
        )
    baseline_mean = sum(baseline_ms) / len(baseline_ms)
    instrumented_mean = sum(instrumented_ms) / len(instrumented_ms)
    added = instrumented_mean - baseline_mean
    relative = added / baseline_mean if baseline_mean > 0 else None
    baseline_misses = (
        sum(value > deadline_ms for value in baseline_ms) if deadline_ms is not None else 0
    )
    instrumented_misses = (
        sum(value > deadline_ms for value in instrumented_ms) if deadline_ms is not None else 0
    )
    return ExecutionOverhead(
        len(baseline_ms),
        baseline_mean,
        instrumented_mean,
        added,
        relative,
        baseline_misses,
        instrumented_misses,
        True,
        (),
        timing_provenance,
    )
