from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..contracts import ModelCapabilityProfile
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
    if evaluation.get("missing_outcomes") not in (None, "preserve"):
        raise ValueError("evaluation.missing_outcomes must be 'preserve'")
    if evaluation.get("confirmation_plan") not in (None, "frozen"):
        raise ValueError("evaluation.confirmation_plan must be 'frozen'")
    _validate_resource_budget(evaluation)
    environment_ids = _enabled_environment_ids(spec["environments"])
    expected_attempts = (
        len(environment_ids) * len(conditions) * len(seeds) * int(evaluation.get("repetitions", 1))
    )
    budget = evaluation.get("resource_budget", {})
    if budget.get("max_attempts") is not None and expected_attempts > budget["max_attempts"]:
        raise ValueError("evaluation resource budget max_attempts is smaller than the frozen plan")
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
        environment_ids=environment_ids,
        protocol=_protocol_record(spec),
    ).freeze()


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    return value


def _validate_protocol_sections(spec: dict[str, Any]) -> None:
    model = _mapping(spec.get("model", {}), "model")
    if model and not isinstance(model.get("adapter"), str):
        raise ValueError("model.adapter is required when model is declared")
    _validate_model_capabilities(model, _mapping(spec.get("evaluation", {}), "evaluation"))
    checkpoint = model.get("checkpoint")
    if checkpoint is not None and (
        not isinstance(checkpoint, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", checkpoint) is None
    ):
        raise ValueError("model.checkpoint must be sha256:<lowercase digest>")
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
            if item.get("retry_policy", "none") != "none" or item.get("auto_retry", False):
                raise ValueError(
                    f"physical environment {environment_id} must disable automatic retries"
                )
    if not _enabled_environment_ids(environments):
        raise ValueError("at least one environment must be enabled")
    for section in ("measurement", "outputs"):
        value = spec.get(section, {})
        if not isinstance(value, dict) or any(
            not isinstance(flag, bool) for flag in value.values()
        ):
            raise ValueError(f"{section} must be a mapping of boolean controls")


def _validate_resource_budget(evaluation: dict[str, Any]) -> None:
    budget = evaluation.get("resource_budget", {})
    if not isinstance(budget, dict):
        raise ValueError("evaluation.resource_budget must be a mapping")
    for name, value in budget.items():
        if name not in {
            "max_attempts",
            "max_policy_calls",
            "max_wall_time_ms",
            "max_compute_time_ms",
        }:
            raise ValueError(f"unsupported resource budget field: {name}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"resource budget {name} must be non-negative")
        if name == "max_attempts" and int(value) != value:
            raise ValueError("resource budget max_attempts must be an integer")


def _validate_model_capabilities(model: dict[str, Any], evaluation: dict[str, Any]) -> None:
    declared = model.get("capabilities")
    if declared is None:
        return
    if not isinstance(declared, dict):
        raise ValueError("model.capabilities must be a mapping")
    required = {
        "model_id",
        "family",
        "input_modalities",
        "output_representation",
        "supports_closed_loop",
        "supports_action_chunks",
        "supported_metrics",
    }
    missing = sorted(required - declared.keys())
    if missing:
        raise ValueError("model.capabilities missing: " + ", ".join(missing))
    try:
        profile = ModelCapabilityProfile(
            **{
                **declared,
                "input_modalities": tuple(declared["input_modalities"]),
                "supported_metrics": tuple(declared["supported_metrics"]),
                "runtime_controls": tuple(declared.get("runtime_controls", ())),
                "timing_signals": tuple(declared.get("timing_signals", ())),
            }
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid model.capabilities: {exc}") from exc
    issues = profile.validate()
    if issues:
        raise ValueError("invalid model.capabilities: " + "; ".join(issues))
    strategy = evaluation.get("execution_strategy")
    if strategy == "async" and not profile.supports_async:
        raise ValueError("execution_strategy async requires supports_async")
    if strategy == "streaming" and not profile.supports_streaming:
        raise ValueError("execution_strategy streaming requires supports_streaming")
    if strategy == "cached" and not profile.supports_cached_predictions:
        raise ValueError("execution_strategy cached requires supports_cached_predictions")
    conditions = evaluation.get("conditions", [])
    if any(
        isinstance(condition, dict) and condition.get("action_prefix", 1) > 1
        for condition in conditions
    ):
        if not profile.supports_action_chunks:
            raise ValueError("action_prefix > 1 requires supports_action_chunks")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _enabled_environment_ids(environments: list[Any]) -> tuple[str, ...]:
    enabled: list[str] = []
    for environment in environments:
        item = environment if isinstance(environment, dict) else {}
        # Simulator entries are enabled by default; physical entries require an
        # explicit opt-in so compiling a plan can never authorize hardware by
        # implication.
        default_enabled = item.get("kind") != "physical"
        if item.get("enabled", default_enabled):
            enabled.append(item.get("id", ""))
    return tuple(enabled)


def _protocol_record(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the frozen E=(P,M,S,X,D,O,R) protocol envelope.

    The compiler keeps the user's declared sections intact and records the
    source digest separately. Execution backends can add D/O/R evidence later,
    but cannot replace the frozen protocol without changing the plan digest.
    """
    return {
        "schema": spec["schema"],
        "protocol": spec.get("experiment", {}).get("protocol_revision"),
        "P": {
            "experiment": spec.get("experiment", {}),
            "evaluation": spec.get("evaluation", {}),
        },
        "M": spec.get("model", {}),
        "S": {
            "task": spec.get("task", {}),
            "environments": spec.get("environments", []),
        },
        "X": spec.get("execution", {}),
        "D": {"measurement": spec.get("measurement", {})},
        "O": {"outputs": spec.get("outputs", {})},
        "R": {"source_spec_sha256": _digest(spec)},
    }
