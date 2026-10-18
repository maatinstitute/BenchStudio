from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioContract:
    scenario_id: str
    task_revision: str
    asset_digest_sha256: str
    initial_condition_digest_sha256: str
    success_criterion_version: str


def validate_scenario_pair(
    first: ScenarioContract, second: ScenarioContract, *, allow_asset_exception: bool = False
) -> list[str]:
    issues: list[str] = []
    if first.scenario_id != second.scenario_id:
        issues.append("scenario_id differs")
    if first.task_revision != second.task_revision:
        issues.append("task_revision differs")
    if first.success_criterion_version != second.success_criterion_version:
        issues.append("success_criterion_version differs")
    if first.initial_condition_digest_sha256 != second.initial_condition_digest_sha256:
        issues.append("initial_condition_digest_sha256 differs")
    if first.asset_digest_sha256 != second.asset_digest_sha256 and not allow_asset_exception:
        issues.append("asset_digest_sha256 differs")
    return issues
