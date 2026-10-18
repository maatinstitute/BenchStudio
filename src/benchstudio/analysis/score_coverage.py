from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TerminationReason = Literal[
    "success",
    "failure",
    "scheduled_end",
    "censored",
    "cancelled",
    "infrastructure_failure",
]


@dataclass(frozen=True)
class ScoreCoverage:
    scheduled_steps: int
    observed_steps: int
    scored_steps: int
    post_success_steps: int
    complete: bool
    issues: tuple[str, ...]
    termination_reason: TerminationReason | None = None

    @property
    def coverage_fraction(self) -> float:
        return self.scored_steps / self.scheduled_steps if self.scheduled_steps else 0.0


def audit_score_coverage(
    *,
    scheduled_steps: int,
    observed_steps: int,
    scored_steps: int,
    success_step: int | None = None,
    termination_reason: TerminationReason | None = None,
) -> ScoreCoverage:
    issues: list[str] = []
    counts = {
        "scheduled_steps": scheduled_steps,
        "observed_steps": observed_steps,
        "scored_steps": scored_steps,
    }
    invalid_counts = [
        name
        for name, value in counts.items()
        if not isinstance(value, int) or isinstance(value, bool)
    ]
    if invalid_counts:
        issues.append("counts must be non-negative integers: " + ", ".join(invalid_counts))
    valid_count_values = not invalid_counts
    valid_termination_reasons = {
        None,
        "success",
        "failure",
        "scheduled_end",
        "censored",
        "cancelled",
        "infrastructure_failure",
    }
    if valid_count_values and min(scheduled_steps, observed_steps, scored_steps) < 0:
        issues.append("counts must be non-negative")
    if termination_reason is not None and (
        not isinstance(termination_reason, str)
        or termination_reason not in valid_termination_reasons
    ):
        issues.append("termination_reason is invalid")
    if valid_count_values and observed_steps > scheduled_steps:
        issues.append("observed_steps exceeds scheduled_steps")
    if valid_count_values and scored_steps > observed_steps:
        issues.append("scored_steps exceeds observed_steps")
    post_success_steps = 0
    if success_step is not None:
        valid_success_step = isinstance(success_step, int) and not isinstance(success_step, bool)
        if not valid_success_step or success_step < 0:
            issues.append("success_step must be a non-negative integer")
        else:
            post_success_steps = max(0, observed_steps - success_step - 1)
            if valid_count_values and success_step >= observed_steps:
                issues.append("success_step is outside observed steps")
    declared_early_success = termination_reason == "success" and success_step is not None
    if success_step is not None and termination_reason not in {None, "success"}:
        issues.append("success_step requires success termination")
    if declared_early_success and valid_count_values and success_step != observed_steps - 1:
        issues.append("success termination must be the final observed step")
    if declared_early_success and valid_count_values and scored_steps != observed_steps:
        issues.append("early success requires every observed step to be scored")
    complete = (
        valid_count_values
        and not issues
        and (
            (observed_steps == scheduled_steps and scored_steps == scheduled_steps)
            or declared_early_success
        )
    )
    if not complete and not issues:
        if termination_reason in {"censored", "cancelled", "infrastructure_failure"}:
            issues.append(f"evaluation is incomplete: {termination_reason}")
        else:
            issues.append("score does not cover the scheduled evaluation")
    return ScoreCoverage(
        scheduled_steps,
        observed_steps,
        scored_steps,
        post_success_steps,
        complete,
        tuple(issues),
        termination_reason,
    )
