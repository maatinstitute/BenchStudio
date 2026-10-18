from __future__ import annotations

from typing import Any

from .frozen_plan import CampaignPlanner, FrozenCampaignPlan


def compile_campaign_spec(spec: dict[str, Any]) -> FrozenCampaignPlan:
    """Compile a declarative campaign mapping into an immutable execution plan."""
    if spec.get("schema") != "benchstudio.campaign.v1":
        raise ValueError("unsupported or missing campaign schema")
    experiment = _mapping(spec.get("experiment"), "experiment")
    task = _mapping(spec.get("task"), "task")
    evaluation = _mapping(spec.get("evaluation"), "evaluation")
    run_id = experiment.get("name")
    scenario_id = task.get("task_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("experiment.name is required")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ValueError("task.task_id is required")
    seeds = evaluation.get("seeds")
    conditions = evaluation.get("conditions")
    if not isinstance(seeds, list) or not all(isinstance(seed, int) for seed in seeds):
        raise ValueError("evaluation.seeds must be a list of integers")
    if (
        not isinstance(conditions, list)
        or not conditions
        or not all(isinstance(item, dict) for item in conditions)
    ):
        raise ValueError("evaluation.conditions must be a non-empty list of mappings")
    if evaluation.get("paired") is not True:
        raise ValueError("evaluation.paired must be true for this compiler")
    return CampaignPlanner(
        run_id=run_id,
        scenario_id=scenario_id,
        conditions=conditions,
        seeds=seeds,
        repetitions=int(evaluation.get("repetitions", 1)),
        scenario_pack_digest=(
            task.get("scenario_pack_digest")
            if isinstance(task.get("scenario_pack_digest"), str)
            else None
        ),
    ).freeze()


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    return value
