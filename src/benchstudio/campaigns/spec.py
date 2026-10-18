from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..calibration import CalibrationRecord
from ..contracts import ModelCapabilityProfile
from ..validity import BenchmarkValidityRecord
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
    if not isinstance(seeds, list) or not all(
        isinstance(seed, int) and not isinstance(seed, bool) for seed in seeds
    ):
        raise ValueError("evaluation.seeds must be a list of integers")
    if (
        not isinstance(conditions, list)
        or not conditions
        or not all(isinstance(item, dict) for item in conditions)
    ):
        raise ValueError("evaluation.conditions must be a non-empty list of mappings")
    _validate_condition_controls(conditions)
    _validate_protocol_sections(spec)
    if evaluation.get("paired") is not True:
        raise ValueError("evaluation.paired must be true for this compiler")
    if evaluation.get("missing_outcomes") not in (None, "preserve"):
        raise ValueError("evaluation.missing_outcomes must be 'preserve'")
    if evaluation.get("confirmation_plan") not in (None, "frozen"):
        raise ValueError("evaluation.confirmation_plan must be 'frozen'")
    repetitions = evaluation.get("repetitions", 1)
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("evaluation.repetitions must be a positive integer")
    _validate_resource_budget(evaluation)
    environment_ids = _enabled_environment_ids(spec["environments"])
    expected_attempts = len(environment_ids) * len(conditions) * len(seeds) * repetitions
    budget = evaluation.get("resource_budget", {})
    if budget.get("max_attempts") is not None and expected_attempts > budget["max_attempts"]:
        raise ValueError("evaluation resource budget max_attempts is smaller than the frozen plan")
    return CampaignPlanner(
        run_id=run_id,
        scenario_id=scenario_id,
        conditions=conditions,
        seeds=seeds,
        repetitions=repetitions,
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


def _validate_condition_controls(conditions: list[dict[str, Any]]) -> None:
    for index, condition in enumerate(conditions):
        label = f"evaluation.conditions[{index}]"
        if "id" in condition and (not isinstance(condition["id"], str) or not condition["id"]):
            raise ValueError(f"{label}.id must be a non-empty string")
        denoising_steps = condition.get("denoising_steps")
        if denoising_steps is not None and (
            isinstance(denoising_steps, bool)
            or not isinstance(denoising_steps, int)
            or denoising_steps < 0
        ):
            raise ValueError(f"{label}.denoising_steps must be a non-negative integer or null")
        for field in ("action_prefix", "observation_refresh_ticks", "max_episode_steps"):
            value = condition.get(field)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                raise ValueError(f"{label}.{field} must be a positive integer")
        strategy = condition.get("execution_strategy")
        if strategy is not None and (
            not isinstance(strategy, str)
            or strategy not in {"sync", "async", "streaming", "cached"}
        ):
            raise ValueError(f"{label}.execution_strategy is unsupported")
        max_cache_entries = condition.get("max_cache_entries")
        if max_cache_entries is not None and (
            isinstance(max_cache_entries, bool)
            or not isinstance(max_cache_entries, int)
            or max_cache_entries < 1
        ):
            raise ValueError(f"{label}.max_cache_entries must be a positive integer")


def _validate_protocol_sections(spec: dict[str, Any]) -> None:
    model = _mapping(spec.get("model", {}), "model")
    if model and not isinstance(model.get("adapter"), str):
        raise ValueError("model.adapter is required when model is declared")
    if "adapter_config" in model and not isinstance(model["adapter_config"], dict):
        raise ValueError("model.adapter_config must be a mapping")
    if model.get("adapter") == "trace":
        adapter_config = model.get("adapter_config")
        if not isinstance(adapter_config, dict) or not isinstance(adapter_config.get("path"), str):
            raise ValueError("trace model.adapter_config.path is required")
        trace_sha256 = adapter_config.get("trace_sha256")
        if not isinstance(trace_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", trace_sha256) is None:
            raise ValueError(
                "trace model.adapter_config.trace_sha256 must be lowercase SHA-256 hex"
            )
    task = _mapping(spec.get("task"), "task")
    if "task_revision" in task and (
        not isinstance(task["task_revision"], str) or not task["task_revision"]
    ):
        raise ValueError("task.task_revision must be a non-empty string")
    if "scenario_pack_digest" in task:
        digest = task["scenario_pack_digest"]
        if not isinstance(digest, str) or re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", digest) is None:
            raise ValueError("task.scenario_pack_digest must be a SHA-256 digest")
    evaluation = _mapping(spec.get("evaluation", {}), "evaluation")
    execution = spec.get("execution", {})
    if not isinstance(execution, dict):
        raise ValueError("execution must be a mapping")
    clock_domains = execution.get("clock_domains")
    if clock_domains is not None and (
        not isinstance(clock_domains, list)
        or not clock_domains
        or not all(isinstance(value, str) and value for value in clock_domains)
    ):
        raise ValueError("execution.clock_domains must be a non-empty list of strings")
    for field in ("controller_deadline_ns", "queue_capacity"):
        value = execution.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError(f"execution.{field} must be a non-negative integer")
    strategy = evaluation.get("execution_strategy", "sync")
    if not isinstance(strategy, str) or strategy not in {
        "sync",
        "async",
        "streaming",
        "cached",
    }:
        raise ValueError(f"unsupported evaluation.execution_strategy: {strategy}")
    _validate_model_capabilities(model, evaluation)
    max_cache_entries = evaluation.get("max_cache_entries", 256)
    if (
        isinstance(max_cache_entries, bool)
        or not isinstance(max_cache_entries, int)
        or max_cache_entries < 1
    ):
        raise ValueError("evaluation.max_cache_entries must be a positive integer")
    if "validity" in evaluation:
        BenchmarkValidityRecord.from_mapping(evaluation["validity"], field="evaluation.validity")
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
        if "adapter" in item and (not isinstance(item["adapter"], str) or not item["adapter"]):
            raise ValueError(f"environment {environment_id} adapter must be a non-empty string")
        if "adapter_config" in item and not isinstance(item["adapter_config"], dict):
            raise ValueError(f"environment {environment_id} adapter_config must be a mapping")
        if "calibration" in item:
            CalibrationRecord.from_mapping(
                item["calibration"], field=f"environment {environment_id}.calibration"
            )
        requirements = item.get("required_capabilities", {})
        if not isinstance(requirements, dict) or any(
            not isinstance(name, str) or not isinstance(value, bool)
            for name, value in requirements.items()
        ):
            raise ValueError(
                f"environment {environment_id} required_capabilities must map names to booleans"
            )
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
            "max_gpu_hours",
            "max_bytes",
            "max_policy_queries",
            "retry_limit",
            "per_cell_timeout_seconds",
        }:
            raise ValueError(f"unsupported resource budget field: {name}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"resource budget {name} must be non-negative")
        if name == "max_attempts" and int(value) != value:
            raise ValueError("resource budget max_attempts must be an integer")
        if name in {"max_bytes", "max_policy_queries", "retry_limit"} and int(value) != value:
            raise ValueError(f"resource budget {name} must be an integer")


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
    for field in ("input_modalities", "supported_metrics", "runtime_controls", "timing_signals"):
        value = declared.get(field, ())
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"model.capabilities.{field} must be a list or tuple")
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
    strategies = {evaluation.get("execution_strategy", "sync")}
    conditions = evaluation.get("conditions", [])
    strategies.update(
        condition["execution_strategy"]
        for condition in conditions
        if isinstance(condition, dict) and "execution_strategy" in condition
    )
    for strategy in strategies:
        if strategy == "async" and not profile.supports_async:
            raise ValueError(f"execution_strategy {strategy} requires supports_async")
        if strategy == "streaming" and not profile.supports_streaming:
            raise ValueError(f"execution_strategy {strategy} requires supports_streaming")
        if strategy == "cached" and not profile.supports_cached_predictions:
            raise ValueError(f"execution_strategy {strategy} requires supports_cached_predictions")
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
    evaluation = spec.get("evaluation", {})
    execution = dict(spec.get("execution", {}))
    if isinstance(evaluation, dict):
        execution.setdefault("strategy", evaluation.get("execution_strategy", "sync"))
        execution.setdefault("max_cache_entries", evaluation.get("max_cache_entries", 256))
        execution.setdefault(
            "condition_controls",
            [
                {
                    key: condition[key]
                    for key in (
                        "id",
                        "denoising_steps",
                        "action_prefix",
                        "observation_refresh_ticks",
                        "max_episode_steps",
                        "execution_strategy",
                        "max_cache_entries",
                    )
                    if isinstance(condition, dict) and key in condition
                }
                for condition in evaluation.get("conditions", [])
            ],
        )
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
        "X": execution,
        "D": {"measurement": spec.get("measurement", {})},
        "O": {"outputs": spec.get("outputs", {})},
        "R": {"source_spec_sha256": _digest(spec)},
    }
