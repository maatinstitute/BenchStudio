from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Literal

from .analysis.resources import ResourceBudget, audit_resources
from .conformance import ActionSpec, PolicySession, validate_observation
from .contracts import Policy, Simulator
from .evidence import (
    NdjsonWriter,
    build_artifact_manifest,
    environment_fingerprint,
    write_manifest_trust_anchor,
)
from .measurement import ResourceSampler, delta_resources, sample_resources
from .runtime_receipts import build_runtime_receipt, write_runtime_receipt


@dataclass(frozen=True)
class RunConfig:
    run_id: str | None = None
    attempt_id: str | None = None
    plan_digest_sha256: str | None = None
    worker_id: str | None = None
    task_id: str = "mock_task"
    robot_id: str = "mock_robot"
    environment_id: str = "default"
    planned_condition_id: str | None = None
    seed: int = 42
    episodes: int = 1
    denoising_steps: int | None = 2
    action_prefix: int = 2
    observation_refresh_ticks: int = 1
    max_episode_steps: int = 100
    initial_condition_id: str = "default"
    action_spec: ActionSpec | None = None
    policy_timeout_ns: int | None = None
    execution_strategy: Literal["sync", "async", "streaming", "cached"] = "sync"
    max_cache_entries: int = 256
    calibration: dict[str, Any] | None = None
    benchmark_validity: dict[str, Any] | None = None
    model_reference: dict[str, Any] | None = None
    resource_budget: ResourceBudget | None = None

    def __post_init__(self) -> None:
        if self.episodes < 1:
            raise ValueError("episodes must be positive")
        if self.action_prefix < 1:
            raise ValueError("action_prefix must be positive")
        if self.observation_refresh_ticks < 1:
            raise ValueError("observation_refresh_ticks must be positive")
        if self.max_episode_steps < 1:
            raise ValueError("max_episode_steps must be positive")
        if self.policy_timeout_ns is not None and self.policy_timeout_ns < 0:
            raise ValueError("policy_timeout_ns must be non-negative")
        if self.execution_strategy not in {"sync", "async", "streaming", "cached"}:
            raise ValueError(f"unsupported execution strategy: {self.execution_strategy}")
        if self.max_cache_entries < 1:
            raise ValueError("max_cache_entries must be positive")
        if self.calibration is not None and not isinstance(self.calibration, dict):
            raise ValueError("calibration must be a mapping")
        if self.benchmark_validity is not None and not isinstance(self.benchmark_validity, dict):
            raise ValueError("benchmark_validity must be a mapping")
        if self.model_reference is not None and not isinstance(self.model_reference, dict):
            raise ValueError("model_reference must be a mapping")
        if not self.environment_id:
            raise ValueError("environment_id must not be empty")


@dataclass(frozen=True)
class EpisodeResult:
    episode_id: str
    pair_id: str
    condition_id: str
    success: bool
    status: str
    termination_reason: str
    steps: int
    policy_calls: int
    observation_count: int
    duration_ms: float
    mean_observation_age_ms: float
    p95_observation_age_ms: float
    mean_policy_latency_ms: float
    p95_policy_latency_ms: float
    action_prefix: int
    resource_metrics: dict[str, float | int | str] = field(default_factory=dict)
    error: str | None = None
    initial_condition_id: str | None = None
    planned_condition_id: str | None = None


def run_episodes(
    policy: Policy,
    simulator: Simulator,
    config: RunConfig,
    output: Path,
    *,
    resource_sampler: ResourceSampler | None = None,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    started_monotonic_ns = time.monotonic_ns()
    manifest = _manifest(policy, simulator, config)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    episode_results: list[EpisodeResult] = []
    trace_writer = NdjsonWriter(output / "episodes.jsonl")
    campaign_status = "completed"
    try:
        for index in range(config.episodes):
            result, _events = _run_episode(
                policy,
                simulator,
                config,
                index,
                emit=trace_writer.write,
                retain_events=False,
                resource_sampler=resource_sampler,
            )
            episode_results.append(result)
            if result.status not in {"success", "failure"}:
                campaign_status = "failed"
    except Exception as exc:
        campaign_status = "failed"
        episode_results.append(_campaign_failure(len(episode_results), exc))
    finally:
        try:
            trace_writer.close()
        except Exception as exc:
            campaign_status = "failed_cleanup"
            episode_results.append(
                _campaign_failure_with_status(len(episode_results), exc, status="trace_close_error")
            )
        try:
            simulator.close()
        except Exception as exc:
            campaign_status = "failed_cleanup"
            episode_results.append(
                _campaign_failure_with_status(len(episode_results), exc, status="cleanup_error")
            )
        try:
            close_policy = getattr(policy, "close", None)
            if close_policy is not None:
                close_policy()
        except Exception as exc:
            campaign_status = "failed_cleanup"
            episode_results.append(
                _campaign_failure_with_status(
                    len(episode_results), exc, status="policy_close_error"
                )
            )
    summary = _summary(config, episode_results, campaign_status=campaign_status)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_runtime_receipt(
        output / "runtime-receipt.json",
        build_runtime_receipt(
            run_id=config.run_id,
            attempt_id=config.attempt_id,
            plan_digest_sha256=config.plan_digest_sha256,
            worker_id=config.worker_id,
            status=campaign_status,
            started_monotonic_ns=started_monotonic_ns,
            completed_monotonic_ns=time.monotonic_ns(),
            backend_id=simulator.simulator_id,
            environment=manifest["environment"],
        ),
    )
    artifact_manifest = build_artifact_manifest(output, status=campaign_status)
    artifact_manifest_path = output / "artifact-manifest.json"
    artifact_manifest_path.write_text(
        json.dumps(artifact_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_manifest_trust_anchor(
        artifact_manifest_path, output.parent / f"{output.name}.artifact-manifest.sha256"
    )
    return summary


def _run_episode(
    policy: Policy,
    simulator: Simulator,
    config: RunConfig,
    index: int,
    emit: Callable[[dict[str, Any]], None] | None = None,
    retain_events: bool = True,
    resource_sampler: ResourceSampler | None = None,
) -> tuple[EpisodeResult, list[dict[str, Any]]]:
    episode_scope = config.attempt_id or config.run_id or "standalone"
    episode_id = f"{episode_scope}-episode-{index:04d}"
    seed = config.seed + index
    pair_id = _pair_id(config, seed)
    condition_id = _condition_id(config)
    events: list[dict[str, Any]] = []
    session = PolicySession(
        f"{episode_id}-policy-session",
        policy,
        action_spec=config.action_spec,
        execution_strategy=config.execution_strategy,
        max_cache_entries=config.max_cache_entries,
    )

    def record(event: dict[str, Any]) -> None:
        if retain_events:
            events.append(event)
        if emit is not None:
            emit(event)

    ages: list[float] = []
    latencies: list[float] = []
    policy_calls = 0
    observation_count = 1
    steps = 0
    start = time.perf_counter_ns()
    resource_before = sample_resources(resource_sampler)
    try:
        session.initialize(seed=seed)
        session.start()
    except Exception as exc:
        return _failed_episode(
            episode_id,
            start,
            steps,
            policy_calls,
            observation_count,
            ages,
            latencies,
            config,
            events,
            pair_id=pair_id,
            condition_id=condition_id,
            status="policy_reset_error",
            error=exc,
        )
    try:
        observation = simulator.reset(seed=seed)
        observation_issues = validate_observation(observation)
        if observation_issues:
            raise ValueError(
                "invalid observation: " + "; ".join(issue.code for issue in observation_issues)
            )
    except Exception as exc:
        return _failed_episode(
            episode_id,
            start,
            steps,
            policy_calls,
            observation_count,
            ages,
            latencies,
            config,
            events,
            pair_id=pair_id,
            condition_id=condition_id,
            status="simulator_reset_error",
            error=exc,
        )
    termination_reason = "max_episode_steps"
    while not simulator.is_done() and steps < config.max_episode_steps:
        source_observation = observation
        inference_id = f"{episode_id}-inference-{policy_calls:04d}"
        inference_started_ns = time.monotonic_ns()
        try:
            prediction = session.predict(
                source_observation,
                denoising_steps=config.denoising_steps,
                timeout_ns=config.policy_timeout_ns,
            )
            if not prediction.accepted or prediction.action_chunk is None:
                raise RuntimeError(f"{prediction.status}: " + "; ".join(prediction.errors))
            action_chunk = prediction.action_chunk
        except Exception as exc:
            return _failed_episode(
                episode_id,
                start,
                steps,
                policy_calls,
                observation_count,
                ages,
                latencies,
                config,
                events,
                pair_id=pair_id,
                condition_id=condition_id,
                status="policy_inference_error",
                error=exc,
            )
        inference_finished_ns = time.monotonic_ns()
        latency_ms = (inference_finished_ns - inference_started_ns) / 1_000_000
        latencies.append(latency_ms)
        policy_calls += 1
        chunk = action_chunk.actions[: config.action_prefix]
        if not chunk:
            termination_reason = "empty_action_chunk"
            break
        for action_index, action in enumerate(chunk):
            if steps >= config.max_episode_steps or simulator.is_done():
                break
            action_id = f"{inference_id}-action-{action_index:04d}"
            submitted_ns = time.monotonic_ns()
            step_start = time.monotonic_ns()
            try:
                next_observation = simulator.step(action)
                observation_issues = validate_observation(next_observation)
                if observation_issues:
                    raise ValueError(
                        "invalid observation: "
                        + "; ".join(issue.code for issue in observation_issues)
                    )
            except Exception as exc:
                return _failed_episode(
                    episode_id,
                    start,
                    steps,
                    policy_calls,
                    observation_count,
                    ages,
                    latencies,
                    config,
                    events,
                    pair_id=pair_id,
                    condition_id=condition_id,
                    status="simulator_step_error",
                    error=exc,
                )
            executed_ns = time.monotonic_ns()
            execution_ms = (executed_ns - step_start) / 1_000_000
            age_ms = max(0.0, (next_observation.sim_time_s - source_observation.sim_time_s) * 1000)
            ages.append(age_ms)
            record(
                {
                    "schema": "benchstudio.event.v1",
                    "event_type": "action_executed",
                    "episode_id": episode_id,
                    "pair_id": pair_id,
                    "condition_id": condition_id,
                    "action_id": action_id,
                    "step": steps,
                    "inference_id": inference_id,
                    "source_observation_id": _observation_id(
                        episode_id, source_observation.sequence
                    ),
                    "source_observation_sequence": source_observation.sequence,
                    "next_observation_sequence": next_observation.sequence,
                    "inference_started_monotonic_ns": inference_started_ns,
                    "inference_finished_monotonic_ns": inference_finished_ns,
                    "action_submitted_monotonic_ns": submitted_ns,
                    "execution_timestamp_ns": executed_ns,
                    "execution_timestamp_domain": "host_monotonic",
                    "execution_timestamp_status": "simulator_step_returned",
                    "source_sim_time_ns": round(source_observation.sim_time_s * 1_000_000_000),
                    "source_timestamp_domain": (
                        source_observation.source_timestamp.domain
                        if source_observation.source_timestamp is not None
                        else "sim_time"
                    ),
                    "source_timestamp_value_ns": (
                        source_observation.source_timestamp.value_ns
                        if source_observation.source_timestamp is not None
                        else None
                    ),
                    "source_timestamp_uncertainty_ns": (
                        source_observation.source_timestamp.uncertainty_ns
                        if source_observation.source_timestamp is not None
                        else None
                    ),
                    "next_timestamp_domain": (
                        next_observation.source_timestamp.domain
                        if next_observation.source_timestamp is not None
                        else "sim_time"
                    ),
                    "next_timestamp_value_ns": (
                        next_observation.source_timestamp.value_ns
                        if next_observation.source_timestamp is not None
                        else None
                    ),
                    "next_timestamp_uncertainty_ns": (
                        next_observation.source_timestamp.uncertainty_ns
                        if next_observation.source_timestamp is not None
                        else None
                    ),
                    "action_digest_sha256": _digest_action(action),
                    "observation_age_ms": round(age_ms, 6),
                    "observation_age_status": "sim_time_delta",
                    "inference_to_dispatch_ms": round(
                        (submitted_ns - inference_finished_ns) / 1_000_000, 6
                    ),
                    "observation_to_execution_host_ms": _host_age_ms(
                        source_observation, executed_ns
                    ),
                    "policy_latency_ms": round(latency_ms, 6),
                    "action_execution_ms": round(execution_ms, 6),
                    "action_prefix": config.action_prefix,
                    "action_index": action_index,
                    "denoising_steps": config.denoising_steps,
                    "policy_metadata": _metadata_for_evidence(action_chunk.metadata),
                    "execution_strategy": prediction.execution_strategy,
                    "cache_hit": prediction.cache_hit,
                }
            )
            # Refreshing is deliberately controlled outside the policy. When a
            # refresh interval is larger than one, the policy continues to see
            # the previous observation while the simulator advances.
            observation_count += 1
            steps += 1
            if steps % config.observation_refresh_ticks == 0:
                observation = next_observation
            if simulator.is_done():
                termination_reason = "environment_done"
                break
    if simulator.is_success():
        termination_reason = "success"
    elif simulator.is_done() and termination_reason != "success":
        termination_reason = "failure"
    session.stop()
    resource_after = sample_resources(resource_sampler)
    resource_metrics = delta_resources(resource_before, resource_after)
    record(
        {
            "schema": "benchstudio.event.v1",
            "event_type": "resource_measurement",
            "episode_id": episode_id,
            "pair_id": pair_id,
            "condition_id": condition_id,
            "before": resource_before,
            "after": resource_after,
            "delta": resource_metrics,
        }
    )
    duration_ms = (time.perf_counter_ns() - start) / 1_000_000
    return EpisodeResult(
        episode_id=episode_id,
        pair_id=pair_id,
        condition_id=condition_id,
        success=simulator.is_success(),
        status="success" if simulator.is_success() else "failure",
        termination_reason=termination_reason,
        steps=steps,
        policy_calls=policy_calls,
        observation_count=observation_count,
        duration_ms=round(duration_ms, 6),
        mean_observation_age_ms=round(mean(ages), 6) if ages else 0.0,
        p95_observation_age_ms=round(_percentile(ages, 0.95), 6),
        mean_policy_latency_ms=round(mean(latencies), 6) if latencies else 0.0,
        p95_policy_latency_ms=round(_percentile(latencies, 0.95), 6),
        action_prefix=config.action_prefix,
        resource_metrics=resource_metrics,
        initial_condition_id=config.initial_condition_id,
        planned_condition_id=config.planned_condition_id,
    ), events


def _failed_episode(
    episode_id: str,
    start_ns: int,
    steps: int,
    policy_calls: int,
    observation_count: int,
    ages: list[float],
    latencies: list[float],
    config: RunConfig,
    events: list[dict[str, Any]],
    pair_id: str,
    condition_id: str,
    *,
    status: str,
    error: Exception,
) -> tuple[EpisodeResult, list[dict[str, Any]]]:
    return EpisodeResult(
        episode_id=episode_id,
        pair_id=pair_id,
        condition_id=condition_id,
        success=False,
        status=status,
        termination_reason=status,
        steps=steps,
        policy_calls=policy_calls,
        observation_count=observation_count,
        duration_ms=round((time.perf_counter_ns() - start_ns) / 1_000_000, 6),
        mean_observation_age_ms=round(mean(ages), 6) if ages else 0.0,
        p95_observation_age_ms=round(_percentile(ages, 0.95), 6),
        mean_policy_latency_ms=round(mean(latencies), 6) if latencies else 0.0,
        p95_policy_latency_ms=round(_percentile(latencies, 0.95), 6),
        action_prefix=config.action_prefix,
        error=f"{type(error).__name__}: {error}",
        initial_condition_id=config.initial_condition_id,
        planned_condition_id=config.planned_condition_id,
    ), events


def _observation_id(episode_id: str, sequence: int) -> str:
    return f"{episode_id}-observation-{sequence:06d}"


def _digest_action(action: Any) -> str:
    payload = json.dumps(action, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _metadata_for_evidence(metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep adapter metadata JSON-safe and deterministic in action evidence."""
    try:
        return json.loads(json.dumps(metadata, sort_keys=True, default=str))
    except (TypeError, ValueError, RecursionError) as exc:
        return {"serialization_error": f"{type(exc).__name__}: {exc}"}


def _host_age_ms(observation: Any, end_ns: int) -> float | None:
    received_ns = getattr(observation, "received_monotonic_ns", None)
    if received_ns is None:
        return None
    return round(max(0, end_ns - received_ns) / 1_000_000, 6)


def _manifest(policy: Policy, simulator: Simulator, config: RunConfig) -> dict[str, Any]:
    config_payload = asdict(config)
    digest = hashlib.sha256(json.dumps(config_payload, sort_keys=True).encode()).hexdigest()
    capabilities = getattr(policy, "__benchstudio_capabilities__", None)
    capability_record = capabilities.to_dict() if hasattr(capabilities, "to_dict") else capabilities
    manifest = {
        "schema": "benchstudio_run_manifest_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy_id": policy.policy_id,
        "simulator_id": simulator.simulator_id,
        "config": config_payload,
        "config_digest_sha256": digest,
        "condition_id": _condition_id(config),
        "runtime": {"python": sys.version, "platform": platform.platform()},
        "environment": environment_fingerprint(simulator.simulator_id),
    }
    if capability_record is not None:
        manifest["model_capabilities"] = capability_record
        manifest["model_adapter_id"] = getattr(policy, "__benchstudio_adapter_id__", None)
    if config.calibration is not None:
        from .calibration import CalibrationRecord

        record = CalibrationRecord.from_mapping(config.calibration)
        manifest["calibration"] = record.to_dict()
        manifest["calibration_digest_sha256"] = record.digest_sha256()
    if config.benchmark_validity is not None:
        from .validity import BenchmarkValidityRecord

        manifest["benchmark_validity"] = BenchmarkValidityRecord.from_mapping(
            config.benchmark_validity
        ).to_dict()
    if config.model_reference is not None:
        manifest["model_reference"] = dict(config.model_reference)
    return manifest


def _summary(
    config: RunConfig, results: list[EpisodeResult], *, campaign_status: str
) -> dict[str, Any]:
    successes = sum(result.success for result in results)
    completed = sum(result.status in {"success", "failure"} for result in results)
    failed = sum(
        result.condition_id != "campaign" and result.status not in {"success", "failure"}
        for result in results
    )
    scheduled = config.episodes
    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
    summary = {
        "schema": "benchstudio_run_summary_v1",
        "task_id": config.task_id,
        "robot_id": config.robot_id,
        "environment_id": config.environment_id,
        "episode_count": len(results),
        "scheduled_episode_count": scheduled,
        "completed_episode_count": completed,
        "failed_episode_count": failed,
        "missing_episode_count": max(0, scheduled - completed - failed),
        "episode_status_counts": status_counts,
        "success_count": successes,
        "completed_success_rate": successes / completed if completed else None,
        "scheduled_success_rate": successes / scheduled if scheduled else None,
        "campaign_status": campaign_status,
        "episodes": [asdict(result) for result in results],
    }
    if config.resource_budget is not None:
        compute_values = [
            result.resource_metrics.get("compute_time_ms")
            for result in results
            if isinstance(result.resource_metrics.get("compute_time_ms"), (int, float))
        ]
        if config.resource_budget.max_compute_time_ms is not None and len(compute_values) != len(
            results
        ):
            summary["resource_budget_audit"] = {
                "valid": False,
                "violations": ["compute_time_unavailable"],
            }
        else:
            audit = audit_resources(
                calls=sum(result.policy_calls for result in results),
                wall_time_ms=sum(result.duration_ms for result in results),
                compute_time_ms=sum(compute_values),
                budget=config.resource_budget,
            )
            summary["resource_budget_audit"] = {
                "valid": audit.valid,
                "violations": list(audit.violations),
            }
    return summary


def _campaign_failure(index: int, error: Exception) -> EpisodeResult:
    return _campaign_failure_with_status(index, error, status="campaign_error")


def _campaign_failure_with_status(index: int, error: Exception, *, status: str) -> EpisodeResult:
    return EpisodeResult(
        episode_id=f"campaign-episode-{index:04d}",
        pair_id=f"campaign-{index:04d}",
        condition_id="campaign",
        success=False,
        status=status,
        termination_reason=status,
        steps=0,
        policy_calls=0,
        observation_count=0,
        duration_ms=0.0,
        mean_observation_age_ms=0.0,
        p95_observation_age_ms=0.0,
        mean_policy_latency_ms=0.0,
        p95_policy_latency_ms=0.0,
        action_prefix=0,
        error=f"{type(error).__name__}: {error}",
    )


def _condition_id(config: RunConfig) -> str:
    payload = {
        "task_id": config.task_id,
        "robot_id": config.robot_id,
        "initial_condition_id": config.initial_condition_id,
        "denoising_steps": config.denoising_steps,
        "action_prefix": config.action_prefix,
        "observation_refresh_ticks": config.observation_refresh_ticks,
        "max_episode_steps": config.max_episode_steps,
        "execution_strategy": config.execution_strategy,
        "max_cache_entries": config.max_cache_entries,
        "calibration": config.calibration,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _pair_id(config: RunConfig, seed: int) -> str:
    payload = {
        "task_id": config.task_id,
        "robot_id": config.robot_id,
        "initial_condition_id": config.initial_condition_id,
        "seed": seed,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
