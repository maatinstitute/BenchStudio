from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RecoverySummary:
    scheduled_pairs: int
    matched_pairs: int
    missing_pairs: int
    nominal_success_rate: float | None
    intervention_success_rate: float | None
    recovery_rate: float | None
    mean_recovery_time_ms: float | None
    issues: tuple[str, ...]


def summarize_recovery_outcomes(records: list[dict[str, Any]]) -> RecoverySummary:
    """Summarize paired nominal/intervention outcomes without imputing branches.

    Records must contain ``pair_id``, ``branch`` (``nominal`` or
    ``intervention``), and a boolean ``success``. Recovery is reported as
    intervention success among matched pairs; it is not inferred from a
    missing nominal or intervention branch.
    """
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    issues: list[str] = []
    for index, record in enumerate(records):
        pair_id = record.get("pair_id")
        branch = record.get("branch")
        if not isinstance(pair_id, str) or not pair_id:
            issues.append(f"record {index}: missing pair_id")
            continue
        if branch not in {"nominal", "intervention"}:
            issues.append(f"record {index}: invalid branch")
            continue
        if branch in grouped.setdefault(pair_id, {}):
            issues.append(f"duplicate {branch} branch for pair {pair_id}")
            continue
        grouped[pair_id][branch] = record
    matched = [
        branches
        for branches in grouped.values()
        if "nominal" in branches and "intervention" in branches
    ]
    missing = len(grouped) - len(matched)
    if missing:
        issues.append("some nominal/intervention branches are missing")
    complete = [
        branches
        for branches in matched
        if isinstance(branches["nominal"].get("success"), bool)
        and isinstance(branches["intervention"].get("success"), bool)
    ]
    if len(complete) < len(matched):
        issues.append("some matched branches have missing outcomes")
    if not complete:
        return RecoverySummary(
            len(grouped),
            0,
            missing,
            None,
            None,
            None,
            None,
            tuple(issues + ["no complete recovery pairs"]),
        )
    recovery_times = [
        float(branches["intervention"]["recovery_time_ms"])
        for branches in complete
        if isinstance(branches["intervention"].get("recovery_time_ms"), (int, float))
        and math.isfinite(float(branches["intervention"]["recovery_time_ms"]))
    ]
    nominal_rate = sum(branches["nominal"]["success"] for branches in complete) / len(complete)
    intervention_rate = sum(branches["intervention"]["success"] for branches in complete) / len(
        complete
    )
    return RecoverySummary(
        len(grouped),
        len(complete),
        missing + len(matched) - len(complete),
        nominal_rate,
        intervention_rate,
        intervention_rate,
        sum(recovery_times) / len(recovery_times) if recovery_times else None,
        tuple(issues),
    )
