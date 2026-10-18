from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .analysis.paired import clopper_pearson_interval

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
    completed = [report for report in reports if report is not None and _is_task_outcome(report)]
    failed = [report for report in reports if report is not None and not _is_task_outcome(report)]
    successes = [report for report in completed if report.get("success")]
    wall_times = [
        float(report["wall_time_s"])
        for report in completed
        if isinstance(report.get("wall_time_s"), (int, float))
    ]
    return {
        "episodes": len(reports),
        "scheduled": len(reports),
        "completed": len(completed),
        "failed": len(failed),
        "missing": len(reports) - len(completed) - len(failed),
        "status_counts": _status_counts(reports),
        "success_count": len(successes),
        "completed_success_rate": len(successes) / len(completed) if completed else None,
        "completed_success_confidence_interval": (
            clopper_pearson_interval(len(successes), len(completed)) if completed else None
        ),
        "scheduled_success_rate": len(successes) / len(reports) if reports else None,
        "scheduled_success_confidence_interval": (
            clopper_pearson_interval(len(successes), len(reports)) if reports else None
        ),
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
    for pair_id in shared_ids:
        report_a = indexed_a[pair_id]
        report_b = indexed_b[pair_id]
        if report_a is None or report_b is None:
            continue
        compared += 1
        agree = bool(report_a.get("success")) == bool(report_b.get("success"))
        agreements += int(agree)
        episodes.append(
            {
                "pair_id": pair_id,
                "condition_id_a": report_a.get("condition_id"),
                "condition_id_b": report_b.get("condition_id"),
                "success_agreement": agree,
                "final_joint_rmse_rad": _joint_rmse(report_a, report_b),
            }
        )
    return {
        "compared_episodes": compared,
        "success_agreement_rate": agreements / compared if compared else None,
        "success_agreement_confidence_interval": (
            clopper_pearson_interval(agreements, compared) if compared else None
        ),
        "unmatched_a": unmatched_a,
        "unmatched_b": unmatched_b,
        "failed_a": _failed_pair_ids(reports_a),
        "failed_b": _failed_pair_ids(reports_b),
        "episodes": episodes,
    }


def _index_reports(reports: list[dict[str, Any] | None]) -> dict[str, dict[str, Any] | None]:
    indexed: dict[str, dict[str, Any] | None] = {}
    for index, report in enumerate(reports):
        if report is None:
            continue
        pair_id = report.get("pair_id")
        if not isinstance(pair_id, str) or not pair_id:
            raise ValueError(
                "every completed report requires a stable pair_id; "
                f"missing at list position {index}"
            )
        if pair_id in indexed:
            raise ValueError(f"duplicate pair_id: {pair_id}")
        if _is_task_outcome(report):
            indexed[pair_id] = report
    return indexed


def _is_task_outcome(report: dict[str, Any]) -> bool:
    status = report.get("status")
    return status is None or status in {"success", "failure"}


def _status_counts(reports: list[dict[str, Any] | None]) -> dict[str, int]:
    counts: dict[str, int] = {"missing": sum(report is None for report in reports)}
    for report in reports:
        if report is None:
            continue
        status = str(report.get("status", "observed"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _failed_pair_ids(reports: list[dict[str, Any] | None]) -> list[str]:
    failed: list[str] = []
    for report in reports:
        if report is None or _is_task_outcome(report):
            continue
        pair_id = report.get("pair_id")
        if isinstance(pair_id, str) and pair_id:
            failed.append(pair_id)
    return sorted(failed)


def _joint_rmse(report_a: dict[str, Any], report_b: dict[str, Any]) -> float | None:
    joints_a = report_a.get("final_joint_positions", {})
    joints_b = report_b.get("final_joint_positions", {})
    if not isinstance(joints_a, dict) or not isinstance(joints_b, dict):
        return None
    shared = sorted(set(joints_a) & set(joints_b))
    pairs: list[tuple[float, float]] = []
    for name in shared:
        try:
            value_a = float(joints_a[name])
            value_b = float(joints_b[name])
        except (TypeError, ValueError):
            continue
        if math.isfinite(value_a) and math.isfinite(value_b):
            pairs.append((value_a, value_b))
    if not pairs:
        return None
    return math.sqrt(sum((value_a - value_b) ** 2 for value_a, value_b in pairs) / len(pairs))


def _mean(values: Any) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    return sum(numeric) / len(numeric) if numeric else None
