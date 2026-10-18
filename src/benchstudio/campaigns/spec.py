from __future__ import annotations

import hashlib
import json
from typing import Any

from .frozen_plan import CampaignPlanner, FrozenCampaignPlan


def compile_campaign_spec(spec: dict[str, Any]) -> FrozenCampaignPlan:
    """Compile a declarative campaign mapping into an immutable execution plan."""
    if spec.get("schema") != "benchstudio.campaign.v1":
        raise ValueError("unsupported or missing campaign schema")
    experiment = _mapping(spec.get("experiment"), "experiment")
    task = _mapping(spec.get("task"), "task")
    evaluation = _mapping(spec.get("evaluation"), "evaluation")
    _validate_protocol_sections(spec)
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
        source_spec_sha256=_digest(spec),
    ).freeze()


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    return value


def _validate_protocol_sections(spec: dict[str, Any]) -> None:
    model = _mapping(spec.get("model", {}), "model")
    if model and not isinstance(model.get("adapter"), str):
        raise ValueError("model.adapter is required when model is declared")
    environments = spec.get("environments", [])
    if not isinstance(environments, list) or not environments:
        raise ValueError("environments must be a non-empty list")
    environment_ids: set[str] = set()
    for environment in environments:
        item = _mapping(environment, "environment")
        environment_id = item.get("id")
        if not isinstance(environment_id, str) or not environment_id:
            raise ValueError("each environment requires a non-empty id")
        if environment_id in environment_ids:
            raise ValueError(f"duplicate environment id: {environment_id}")
        environment_ids.add(environment_id)
        if not isinstance(item.get("kind"), str) or not item["kind"]:
            raise ValueError(f"environment {environment_id} requires kind")
        if item["kind"] == "physical" and item.get("enabled", False):
            if item.get("requires_authorization") is not True:
                raise ValueError(
                    f"physical environment {environment_id} requires explicit authorization"
                )
    for section in ("measurement", "outputs"):
        value = spec.get(section, {})
        if not isinstance(value, dict) or any(
            not isinstance(flag, bool) for flag in value.values()
        ):
            raise ValueError(f"{section} must be a mapping of boolean controls")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
