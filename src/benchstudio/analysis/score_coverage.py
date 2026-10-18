from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreCoverage:
    scheduled_steps: int
    observed_steps: int
    scored_steps: int
    post_success_steps: int
    complete: bool
    issues: tuple[str, ...]

    @property
    def coverage_fraction(self) -> float:
        return self.scored_steps / self.scheduled_steps if self.scheduled_steps else 0.0


def audit_score_coverage(
    *, scheduled_steps: int, observed_steps: int, scored_steps: int, success_step: int | None = None
) -> ScoreCoverage:
    issues: list[str] = []
    if min(scheduled_steps, observed_steps, scored_steps) < 0:
        issues.append("counts must be non-negative")
    if observed_steps > scheduled_steps:
        issues.append("observed_steps exceeds scheduled_steps")
    if scored_steps > observed_steps:
        issues.append("scored_steps exceeds observed_steps")
    post_success_steps = 0
    if success_step is not None:
        post_success_steps = max(0, observed_steps - success_step - 1)
        if success_step >= observed_steps:
            issues.append("success_step is outside observed steps")
    complete = not issues and observed_steps == scheduled_steps and scored_steps == scheduled_steps
    if not complete and not issues:
        issues.append("score does not cover the scheduled evaluation")
    return ScoreCoverage(
        scheduled_steps, observed_steps, scored_steps, post_success_steps, complete, tuple(issues)
    )
