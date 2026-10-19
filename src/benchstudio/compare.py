from __future__ import annotations

import json
import math
from numbers import Real
from pathlib import Path
from typing import Any

from .analysis.paired import clopper_pearson_interval
from .analysis.transfer import summarize_transfer_fidelity
from .campaigns.frozen_plan import FrozenCampaignPlan, load_frozen_campaign_plan

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


def build_campaign_comparison_report(
    *,
    scenario_id: str,
    backend_campaigns: dict[str, Path],
    transfer_backends: tuple[str, str] | None = None,
    transfer_system_id: str = "campaign",
) -> dict[str, Any]:
    """Compare attempt evidence from completed or partially completed campaigns.

    Campaign plans are the ordering authority. Missing attempt directories remain
    missing records, while malformed or failed attempt summaries remain explicit
    execution failures rather than becoming task outcomes.
    """
    reports: dict[str, list[dict[str, Any] | None]] = {}
    errors: dict[str, list[str]] = {}
    plans: dict[str, FrozenCampaignPlan] = {}
    plan_load_issues: list[str] = []
    for backend, root in backend_campaigns.items():
        backend_reports, backend_errors = _load_campaign_reports(root)
        reports[backend] = backend_reports
        if backend_errors:
            errors[backend] = backend_errors
        try:
            plans[backend] = load_frozen_campaign_plan(root / "campaign-plan.json")
        except ValueError as exc:
            message = f"frozen campaign plan is invalid: {exc}"
            errors.setdefault(backend, []).append(message)
            plan_load_issues.append(f"{backend}: {message}")
    compatibility_issues = plan_load_issues + _plan_compatibility_issues(plans)
    if compatibility_issues:
        errors["plan_compatibility"] = compatibility_issues
    report = build_comparison_report(
        scenario_id=scenario_id,
        per_backend_reports=reports,
        per_backend_errors=errors,
    )
    report["plan_compatibility"] = {
        "valid": not compatibility_issues,
        "issues": compatibility_issues,
        "backends": sorted(plans),
    }
    if transfer_backends is not None:
        simulation_backend, physical_backend = transfer_backends
        if simulation_backend not in reports or physical_backend not in reports:
            errors.setdefault("transfer", []).append(
                "transfer backends must both be present in --compare-campaign"
            )
        else:
            report["transfer_fidelity"] = summarize_transfer_fidelity(
                _transfer_records(
                    reports[simulation_backend],
                    reports[physical_backend],
                    system_id=transfer_system_id,
                )
            ).to_dict()
        report["errors"] = {k: v for k, v in errors.items() if v}
    return report


def _plan_compatibility_issues(plans: dict[str, FrozenCampaignPlan]) -> list[str]:
    """Check that compared backends share the frozen experiment semantics.

    Environment declarations are intentionally excluded: transfer comparisons
    are expected to differ in backend and calibration. Task, model, execution,
    condition, seed, and initial-state identities must remain matched.
    """
    if len(plans) < 2:
        return []
    names = sorted(plans)
    reference_name = names[0]
    reference = plans[reference_name]
    reference_signature = _comparison_plan_signature(reference)
    issues: list[str] = []
    for name in names[1:]:
        candidate = plans[name]
        if candidate.run_id != reference.run_id:
            issues.append(
                f"{name}: run_id {candidate.run_id!r} does not match "
                f"{reference_name}: {reference.run_id!r}"
            )
        signature = _comparison_plan_signature(candidate)
        if signature["protocol"] != reference_signature["protocol"]:
            issues.append(f"{name}: frozen task/model/execution protocol does not match {reference_name}")
        if signature["attempts"] != reference_signature["attempts"]:
            issues.append(f"{name}: frozen condition/seed/initial-state schedule does not match {reference_name}")
    return issues


def _comparison_plan_signature(plan: FrozenCampaignPlan) -> dict[str, Any]:
    protocol = plan.protocol or {}
    protocol_copy = json.loads(json.dumps(protocol, sort_keys=True))
    section = protocol_copy.get("S")
    if isinstance(section, dict):
        section.pop("environments", None)
    attempts = sorted(
        (
            attempt.key.scenario_id,
            attempt.key.pair_id,
            attempt.key.condition_id,
            attempt.task_seed,
            attempt.policy_seed,
            json.dumps(attempt.metadata.get("condition", {}), sort_keys=True),
        )
        for attempt in plan.attempts
    )
    return {"protocol": protocol_copy, "attempts": attempts}


def _load_campaign_reports(root: Path) -> tuple[list[dict[str, Any] | None], list[str]]:
    plan_path = root / "campaign-plan.json"
    errors: list[str] = []
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"campaign plan could not be loaded: {type(exc).__name__}: {exc}"]
    attempts = plan.get("attempts") if isinstance(plan, dict) else None
    if not isinstance(attempts, list):
        return [], ["campaign plan attempts must be a list"]
    reports: list[dict[str, Any] | None] = []
    for index, attempt in enumerate(attempts):
        attempt_id = attempt.get("key", {}).get("attempt_id") if isinstance(attempt, dict) else None
        if not isinstance(attempt_id, str) or not attempt_id:
            errors.append(f"attempt {index} has no stable attempt_id")
            reports.append({"pair_id": f"invalid-attempt-{index}", "status": "plan_error"})
            continue
        summary_path = root / "attempts" / attempt_id / "summary.json"
        if not summary_path.is_file():
            reports.append(None)
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{attempt_id}: summary could not be loaded: {type(exc).__name__}: {exc}")
            reports.append({"pair_id": attempt_id, "status": "summary_error"})
            continue
        episodes = summary.get("episodes") if isinstance(summary, dict) else None
        if (
            not isinstance(episodes, list)
            or len(episodes) != 1
            or not isinstance(episodes[0], dict)
        ):
            errors.append(f"{attempt_id}: summary must contain exactly one episode report")
            reports.append({"pair_id": attempt_id, "status": "summary_error"})
            continue
        report = dict(episodes[0])
        original_pair_id = report.get("pair_id")
        key = attempt.get("key", {}) if isinstance(attempt, dict) else {}
        expected_pair_id = key.get("pair_id")
        expected_condition_id = key.get("condition_id")
        condition_id = report.get("condition_id") or expected_condition_id
        if not isinstance(original_pair_id, str) or not original_pair_id:
            errors.append(f"{attempt_id}: episode report is missing pair_id")
            reports.append({"pair_id": attempt_id, "status": "summary_error"})
            continue
        if not isinstance(condition_id, str) or not condition_id:
            errors.append(f"{attempt_id}: episode report is missing condition_id")
            reports.append({"pair_id": attempt_id, "status": "summary_error"})
            continue
        if not isinstance(expected_pair_id, str) or not expected_pair_id:
            errors.append(f"{attempt_id}: frozen plan pair_id is missing")
            reports.append({"pair_id": attempt_id, "status": "summary_error"})
            continue
        planned_condition_id = report.get("planned_condition_id")
        if planned_condition_id is not None and planned_condition_id != expected_condition_id:
            errors.append(f"{attempt_id}: planned_condition_id does not match frozen plan")
            reports.append({"pair_id": attempt_id, "status": "summary_error"})
            continue
        initial_condition_id = report.get("initial_condition_id")
        if initial_condition_id is not None and initial_condition_id != expected_pair_id:
            errors.append(f"{attempt_id}: initial_condition_id does not match frozen plan")
            reports.append({"pair_id": attempt_id, "status": "summary_error"})
            continue
        report["pair_id"] = f"{condition_id}:{original_pair_id}"
        report["original_pair_id"] = original_pair_id
        report["attempt_id"] = attempt_id
        reports.append(report)
    return reports, errors


def _transfer_records(
    simulation: list[dict[str, Any] | None],
    physical: list[dict[str, Any] | None],
    *,
    system_id: str,
) -> list[dict[str, Any]]:
    """Convert paired campaign episode reports into transfer-analysis records."""
    indexed_simulation = _index_all_reports(simulation)
    indexed_physical = _index_all_reports(physical)
    records: list[dict[str, Any]] = []
    for pair_id in sorted(set(indexed_simulation) | set(indexed_physical)):
        simulation_report = indexed_simulation.get(pair_id)
        physical_report = indexed_physical.get(pair_id)
        record: dict[str, Any] = {
            "system_id": system_id,
            "pair_id": pair_id,
            "simulation_success": _success_or_missing(simulation_report),
            "physical_success": _success_or_missing(physical_report),
        }
        if simulation_report is not None:
            age = simulation_report.get("mean_observation_age_ms")
            if isinstance(age, (int, float)):
                record["observation_age_ms"] = age
        records.append(record)
    return records


def _index_all_reports(
    reports: list[dict[str, Any] | None],
) -> dict[str, dict[str, Any] | None]:
    indexed: dict[str, dict[str, Any] | None] = {}
    for report in reports:
        if report is None:
            continue
        pair_id = report.get("pair_id")
        if isinstance(pair_id, str) and pair_id:
            indexed[pair_id] = report
    return indexed


def _success_or_missing(report: dict[str, Any] | None) -> bool | None:
    if report is None or not _is_task_outcome(report):
        return None
    value = report.get("success")
    return value if isinstance(value, bool) else None


def _summarize(reports: list[dict[str, Any] | None]) -> dict[str, Any]:
    completed = [report for report in reports if report is not None and _is_task_outcome(report)]
    failed = [report for report in reports if report is not None and not _is_task_outcome(report)]
    successes = [report for report in completed if report.get("success")]
    wall_times = [
        float(report["wall_time_s"])
        for report in completed
        if _finite_nonnegative(report.get("wall_time_s"))
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
    return status in {None, "success", "failure"} and isinstance(report.get("success"), bool)


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
        if not _finite_real(joints_a[name]) or not _finite_real(joints_b[name]):
            continue
        value_a = float(joints_a[name])
        value_b = float(joints_b[name])
        if math.isfinite(value_a) and math.isfinite(value_b):
            pairs.append((value_a, value_b))
    if not pairs:
        return None
    return math.sqrt(sum((value_a - value_b) ** 2 for value_a, value_b in pairs) / len(pairs))


def _mean(values: Any) -> float | None:
    numeric = [float(value) for value in values if _finite_nonnegative(value)]
    return sum(numeric) / len(numeric) if numeric else None


def _finite_real(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _finite_nonnegative(value: Any) -> bool:
    return _finite_real(value) and value >= 0
