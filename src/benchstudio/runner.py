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
        simulator.close()
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
    policy.reset(seed=seed)
    observation = simulator.reset(seed=seed)
    events: list[dict[str, Any]] = []
    ages: list[float] = []
    latencies: list[float] = []
    policy_calls = 0
    observation_count = 1
    steps = 0
    start = time.perf_counter_ns()
    termination_reason = "max_episode_steps"
    while not simulator.is_done() and steps < config.max_episode_steps:
        source_observation = observation
        inference_id = f"{episode_id}-inference-{policy_calls:04d}"
        request_ns = time.perf_counter_ns()
        action_chunk = policy.predict(source_observation, denoising_steps=config.denoising_steps)
        latency_ms = (time.perf_counter_ns() - request_ns) / 1_000_000
        latencies.append(latency_ms)
        policy_calls += 1
        chunk = action_chunk.actions[: config.action_prefix]
        if not chunk:
            termination_reason = "empty_action_chunk"
            break
        for action_index, action in enumerate(chunk):
            if steps >= config.max_episode_steps or simulator.is_done():
                break
            step_start = time.perf_counter_ns()
            next_observation = simulator.step(action)
            execution_ms = (time.perf_counter_ns() - step_start) / 1_000_000
            age_ms = max(0.0, (next_observation.sim_time_s - source_observation.sim_time_s) * 1000)
            ages.append(age_ms)
            events.append(
                {
                    "episode_id": episode_id,
                    "step": steps,
                    "inference_id": inference_id,
                    "source_observation_sequence": source_observation.sequence,
                    "next_observation_sequence": next_observation.sequence,
                    "observation_age_ms": round(age_ms, 6),
                    "observation_age_status": "sim_time_delta",
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
        "success_rate": successes / len(results) if results else 0.0,
        "completed_success_rate": successes / completed if completed else None,
        "scheduled_success_rate": successes / scheduled if scheduled else None,
        "campaign_status": campaign_status,
        "episodes": [asdict(result) for result in results],
    }


def _campaign_failure(index: int, error: Exception) -> EpisodeResult:
    return EpisodeResult(
        episode_id=f"episode-{index:04d}",
        success=False,
        status="campaign_error",
        termination_reason="campaign_error",
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
