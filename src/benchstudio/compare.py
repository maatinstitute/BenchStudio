from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

COMPARISON_SCHEMA = "benchstudio_comparison_report_v1"


def build_comparison_report(
    *,
    scenario_id: str,
    per_backend_reports: dict[str, list[dict[str, Any] | None]],
    per_backend_errors: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Compare completed episodes and preserve missing/failed episode evidence."""
    backends = sorted(per_backend_reports)
    divergence: dict[str, Any] = {}
    for index, backend_a in enumerate(backends):
        for backend_b in backends[index + 1 :]:
            divergence[f"{backend_a}_vs_{backend_b}"] = _pair_divergence(
                per_backend_reports[backend_a], per_backend_reports[backend_b]
            )
    return {
        "schema": COMPARISON_SCHEMA,
        "scenario_id": scenario_id,
        "backends": backends,
        "summary": {name: _summarize(reports) for name, reports in per_backend_reports.items()},
        "divergence": divergence,
        "errors": {k: v for k, v in (per_backend_errors or {}).items() if v},
    }


def write_comparison_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _summarize(reports: list[dict[str, Any] | None]) -> dict[str, Any]:
    completed = [report for report in reports if report is not None]
    successes = [report for report in completed if report.get("success")]
    wall_times = [
        float(report["wall_time_s"])
        for report in completed
        if isinstance(report.get("wall_time_s"), (int, float))
    ]
    return {
        "episodes": len(reports),
        "completed": len(completed),
        "missing": len(reports) - len(completed),
        "success_count": len(successes),
        "completed_success_rate": len(successes) / len(completed) if completed else None,
        "scheduled_success_rate": len(successes) / len(reports) if reports else None,
        # Compatibility alias uses the conservative scheduled denominator.
        "success_rate": len(successes) / len(reports) if reports else None,
        "mean_time_to_success_s": _mean(report.get("sim_time_s") for report in successes),
        "mean_wall_time_s": sum(wall_times) / len(wall_times) if wall_times else None,
    }


def _pair_divergence(
    reports_a: list[dict[str, Any] | None], reports_b: list[dict[str, Any] | None]
) -> dict[str, Any]:
    indexed_a = _index_reports(reports_a)
    indexed_b = _index_reports(reports_b)
    shared_ids = sorted(set(indexed_a) & set(indexed_b))
    unmatched_a = sorted(set(indexed_a) - set(indexed_b))
    unmatched_b = sorted(set(indexed_b) - set(indexed_a))
    episodes = []
    agreements = 0
    compared = 0
    for episode_id in shared_ids:
        report_a = indexed_a[episode_id]
        report_b = indexed_b[episode_id]
        if report_a is None or report_b is None:
            continue
        compared += 1
        agree = bool(report_a.get("success")) == bool(report_b.get("success"))
        agreements += int(agree)
        episodes.append(
            {
                "episode_id": episode_id,
                "success_agreement": agree,
                "final_joint_rmse_rad": _joint_rmse(report_a, report_b),
            }
        )
    return {
        "compared_episodes": compared,
        "success_agreement_rate": agreements / compared if compared else None,
        "unmatched_a": unmatched_a,
        "unmatched_b": unmatched_b,
        "episodes": episodes,
    }


def _index_reports(reports: list[dict[str, Any] | None]) -> dict[str, dict[str, Any] | None]:
    indexed: dict[str, dict[str, Any] | None] = {}
    for index, report in enumerate(reports):
        if report is None:
            continue
        episode_id = report.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError(
                "every completed report requires a stable episode_id; "
                f"missing at list position {index}"
            )
        if episode_id in indexed:
            raise ValueError(f"duplicate episode_id: {episode_id}")
        indexed[episode_id] = report
    return indexed


def _joint_rmse(report_a: dict[str, Any], report_b: dict[str, Any]) -> float | None:
    joints_a = report_a.get("final_joint_positions", {})
    joints_b = report_b.get("final_joint_positions", {})
    shared = sorted(set(joints_a) & set(joints_b))
    if not shared:
        return None
    return math.sqrt(sum((joints_a[name] - joints_b[name]) ** 2 for name in shared) / len(shared))


def _mean(values: Any) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    return sum(numeric) / len(numeric) if numeric else None
