from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .contracts import Policy, Simulator
from .evidence import NdjsonWriter, build_artifact_manifest, environment_fingerprint


@dataclass(frozen=True)
class RunConfig:
    task_id: str = "mock_task"
    robot_id: str = "mock_robot"
    seed: int = 42
    episodes: int = 1
    denoising_steps: int | None = 2
    action_prefix: int = 2
    observation_refresh_ticks: int = 1
    max_episode_steps: int = 100

    def __post_init__(self) -> None:
        if self.episodes < 1:
            raise ValueError("episodes must be positive")
        if self.action_prefix < 1:
            raise ValueError("action_prefix must be positive")
        if self.observation_refresh_ticks < 1:
            raise ValueError("observation_refresh_ticks must be positive")
        if self.max_episode_steps < 1:
            raise ValueError("max_episode_steps must be positive")


@dataclass(frozen=True)
class EpisodeResult:
    episode_id: str
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
    error: str | None = None


def run_episodes(
    policy: Policy, simulator: Simulator, config: RunConfig, output: Path
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(policy, simulator, config)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    episode_results: list[EpisodeResult] = []
    trace_writer = NdjsonWriter(output / "episodes.jsonl")
    campaign_status = "completed"
    try:
        for index in range(config.episodes):
            result, events = _run_episode(policy, simulator, config, index)
            episode_results.append(result)
            for event in events:
                trace_writer.write(event)
    except Exception as exc:
        campaign_status = "failed"
        episode_results.append(_campaign_failure(len(episode_results), exc))
    finally:
        trace_writer.close()
        try:
            simulator.close()
        except Exception as exc:
            campaign_status = "failed_cleanup"
            episode_results.append(
                _campaign_failure_with_status(len(episode_results), exc, status="cleanup_error")
            )
    summary = _summary(config, episode_results, campaign_status=campaign_status)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifact_manifest = build_artifact_manifest(output, status=campaign_status)
    (output / "artifact-manifest.json").write_text(
        json.dumps(artifact_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _run_episode(
    policy: Policy, simulator: Simulator, config: RunConfig, index: int
) -> tuple[EpisodeResult, list[dict[str, Any]]]:
    episode_id = f"episode-{index:04d}"
    seed = config.seed + index
    events: list[dict[str, Any]] = []
    ages: list[float] = []
    latencies: list[float] = []
    policy_calls = 0
    observation_count = 1
    steps = 0
    start = time.perf_counter_ns()
    try:
        policy.reset(seed=seed)
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
            status="policy_reset_error",
            error=exc,
        )
    try:
        observation = simulator.reset(seed=seed)
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
            status="simulator_reset_error",
            error=exc,
        )
    termination_reason = "max_episode_steps"
    while not simulator.is_done() and steps < config.max_episode_steps:
        source_observation = observation
        inference_id = f"{episode_id}-inference-{policy_calls:04d}"
        inference_started_ns = time.monotonic_ns()
        try:
            action_chunk = policy.predict(
                source_observation, denoising_steps=config.denoising_steps
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
                    status="simulator_step_error",
                    error=exc,
                )
            executed_ns = time.monotonic_ns()
            execution_ms = (executed_ns - step_start) / 1_000_000
            age_ms = max(0.0, (next_observation.sim_time_s - source_observation.sim_time_s) * 1000)
            ages.append(age_ms)
            events.append(
                {
                    "schema": "benchstudio.event.v1",
                    "event_type": "action_executed",
                    "episode_id": episode_id,
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
    duration_ms = (time.perf_counter_ns() - start) / 1_000_000
    return EpisodeResult(
        episode_id=episode_id,
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
    *,
    status: str,
    error: Exception,
) -> tuple[EpisodeResult, list[dict[str, Any]]]:
    return EpisodeResult(
        episode_id=episode_id,
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
    ), events


def _observation_id(episode_id: str, sequence: int) -> str:
    return f"{episode_id}-observation-{sequence:06d}"


def _digest_action(action: Any) -> str:
    payload = json.dumps(action, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _host_age_ms(observation: Any, end_ns: int) -> float | None:
    received_ns = getattr(observation, "received_monotonic_ns", None)
    if received_ns is None:
        return None
    return round(max(0, end_ns - received_ns) / 1_000_000, 6)


def _manifest(policy: Policy, simulator: Simulator, config: RunConfig) -> dict[str, Any]:
    config_payload = asdict(config)
    digest = hashlib.sha256(json.dumps(config_payload, sort_keys=True).encode()).hexdigest()
    return {
        "schema": "benchstudio_run_manifest_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy_id": policy.policy_id,
        "simulator_id": simulator.simulator_id,
        "config": config_payload,
        "config_digest_sha256": digest,
        "runtime": {"python": sys.version, "platform": platform.platform()},
        "environment": environment_fingerprint(simulator.simulator_id),
    }


def _summary(
    config: RunConfig, results: list[EpisodeResult], *, campaign_status: str
) -> dict[str, Any]:
    successes = sum(result.success for result in results)
    completed = sum(result.status in {"success", "failure"} for result in results)
    scheduled = config.episodes
    return {
        "schema": "benchstudio_run_summary_v1",
        "task_id": config.task_id,
        "robot_id": config.robot_id,
        "episode_count": len(results),
        "scheduled_episode_count": scheduled,
        "completed_episode_count": completed,
        "missing_episode_count": max(0, scheduled - len(results)),
        "success_count": successes,
        "success_rate": successes / scheduled if scheduled else 0.0,
        "completed_success_rate": successes / completed if completed else None,
        "scheduled_success_rate": successes / scheduled if scheduled else None,
        "campaign_status": campaign_status,
        "episodes": [asdict(result) for result in results],
    }


def _campaign_failure(index: int, error: Exception) -> EpisodeResult:
    return _campaign_failure_with_status(index, error, status="campaign_error")


def _campaign_failure_with_status(index: int, error: Exception, *, status: str) -> EpisodeResult:
    return EpisodeResult(
        episode_id=f"episode-{index:04d}",
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


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
