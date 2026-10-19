"""Source-backed direct-record query recovery for Refinement/Refresh audits."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable


QUERY_RECOVERY_PROTOCOL: dict[str, Any] = {
    "version": 1,
    "design": "Deterministic direct-record query recovery under artificial information suppression",
    "queries": [
        {"id": "success_attempts", "label": "Successes / attempts", "unit": "count / count", "boundary": "All completed attempted episodes in the declared condition, including failures", "required_fields": ["success"]},
        {"id": "generations", "label": "Actual chunk generations", "unit": "count", "boundary": "Measured rollout generations; excludes model loading, reset and warm-up", "required_fields": ["generations"]},
        {"id": "denoise_nfe", "label": "Measured denoise evaluations", "unit": "count", "boundary": "Actual denoise-method entries in measured rollouts; excludes warm-up", "required_fields": ["denoise_nfe"]},
        {"id": "rollout_wall_s", "label": "Total outer rollout wall time", "unit": "s", "boundary": "Sum of outer rollout intervals over all attempts; runtime manifest defines included stages", "required_fields": ["rollout_wall_s"]},
        {"id": "wall_per_attempt_s", "label": "Mean wall time / attempt", "unit": "s / attempt", "boundary": "Total outer rollout wall time / all completed attempts; raw pooled mean, not equal-task weighting", "required_fields": ["rollout_wall_s"]},
        {"id": "wall_per_success_s", "label": "All-attempt wall time / success", "unit": "s / success", "boundary": "Total outer rollout wall time, including failed attempts, / successes; undefined at zero successes", "required_fields": ["rollout_wall_s", "success"], "zero_denominator_rule": "Known zero successes establishes undefined even when wall time is suppressed"},
    ],
    "projections": [
        {"id": "outcomes_only", "short": "O", "fields": ["attempt_id", "success"]},
        {"id": "outcomes_generations", "short": "G", "fields": ["attempt_id", "success", "generations"]},
        {"id": "full_ledger", "short": "L", "fields": ["attempt_id", "success", "generations", "denoise_nfe", "rollout_wall_s"]},
    ],
    "reference": "Completed records independently reconciled against retained step journals by this analyzer",
    "information_contract": "Reduced projections omit solver configuration, source, action-step schedules and timing. Condition identifiers are opaque to the recovery function. Only direct retained fields and the declared arithmetic are queried; the check does not assert that NFE is impossible to derive when solver configuration/source are available.",
    "status_contract": "recovered = defined value obtained; undefined = enough information establishes zero denominator; unknown = required information suppressed. Recovered and undefined count as answered when they match the reference.",
    "limits": "Finite deterministic mechanism check, not a reader study, natural disclosure experiment, independent empirical benefit estimate, or evidence of improved decisions. Full-projection success is a consistency check of deliberately retained fields, not a publication-level utility claim.",
}


def canonical_sha(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def recover_direct_query(query: dict[str, Any], projected_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Answer only from the supplied projection; never consult hidden configuration."""
    rows = list(projected_rows)
    if not rows:
        raise ValueError("Cannot recover queries from an empty condition")
    available = set.intersection(*(set(row) for row in rows))
    query_id = query["id"]
    if query_id == "wall_per_success_s" and "success" in available and sum(row["success"] for row in rows) == 0:
        return {"status": "undefined", "value": None, "used_fields": ["success"], "reason": "Known zero successes; the requested ratio is undefined"}
    missing = sorted(set(query["required_fields"]) - available)
    if missing:
        return {"status": "unknown", "value": None, "missing_fields": missing, "reason": "Required direct records are absent from this artificial projection"}
    if query_id == "success_attempts":
        value: Any = {"successes": sum(row["success"] for row in rows), "attempts": len(rows)}
    elif query_id in ("generations", "denoise_nfe"):
        value = sum(row[query_id] for row in rows)
    elif query_id == "rollout_wall_s":
        value = math.fsum(row["rollout_wall_s"] for row in rows)
    elif query_id == "wall_per_attempt_s":
        value = math.fsum(row["rollout_wall_s"] for row in rows) / len(rows)
    elif query_id == "wall_per_success_s":
        value = math.fsum(row["rollout_wall_s"] for row in rows) / sum(row["success"] for row in rows)
    else:
        raise ValueError(f"Unknown frozen query: {query_id}")
    return {"status": "recovered", "value": value, "used_fields": list(query["required_fields"])}


def query_answer_check(answer: dict[str, Any], reference: dict[str, Any]) -> bool | None:
    if answer["status"] == "unknown":
        return None
    if answer["status"] != reference["status"]:
        return False
    if type(reference["value"]) is float:
        return type(answer["value"]) in (float, int) and math.isclose(answer["value"], reference["value"], rel_tol=1e-12, abs_tol=1e-12)
    return answer["value"] == reference["value"]


def audit_query_recovery(rows: Iterable[dict[str, Any]], runtime: dict[str, Any]) -> dict[str, Any]:
    """Run the fixed four-cell suppression audit over reconciled episode rows."""
    records = list(rows)
    cells = sorted({(row["h"], row["denoising_steps"]) for row in records})
    if cells != [(1, 5), (1, 10), (5, 5), (5, 10)]:
        raise ValueError("Query recovery requires the locked four cells")
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "complete",
        "protocol": QUERY_RECOVERY_PROTOCOL,
        "protocol_sha256": canonical_sha(QUERY_RECOVERY_PROTOCOL),
        "protocol_status": "Fixed code-defined queries/projections; not external preregistration",
        "runtime_manifest_sha256": canonical_sha(runtime),
        "reference_episode_records_sha256": canonical_sha(records),
        "queries_per_cell": len(QUERY_RECOVERY_PROTOCOL["queries"]),
        "cells": [],
        "checks": [],
        "projections": [],
    }
    for index, (h, d) in enumerate(cells):
        selected = [row for row in records if (row["h"], row["denoising_steps"]) == (h, d)]
        flat = [{"attempt_id": row["run_id"], "success": row["success"], "generations": row["counts"]["generations"], "denoise_nfe": row["counts"]["denoise_steps"], "rollout_wall_s": row["timing"]["rollout_wall_s"]} for row in selected]
        wins = sum(row["independent_driver"]["success"] for row in selected)
        wall = math.fsum(row["timing"]["rollout_wall_s"] for row in selected)
        values = {"success_attempts": {"successes": wins, "attempts": len(selected)}, "generations": sum((row["steps"] + h - 1) // h for row in selected), "denoise_nfe": sum(row["counts"]["denoise_steps"] for row in selected), "rollout_wall_s": wall, "wall_per_attempt_s": wall / len(selected), "wall_per_success_s": wall / wins if wins else None}
        references = {key: {"status": "undefined" if key == "wall_per_success_s" and wins == 0 else "recovered", "value": value} for key, value in values.items()}
        report["cells"].append({"cell_id": index, "h": h, "d": d, "attempts": len(selected), "references": references})
        for projection in QUERY_RECOVERY_PROTOCOL["projections"]:
            projected = [{key: row[key] for key in projection["fields"]} for row in flat]
            report["projections"].append({"cell_id": index, "projection": projection["id"], "records_sha256": canonical_sha(projected), "records": projected})
            for query in QUERY_RECOVERY_PROTOCOL["queries"]:
                answer = recover_direct_query(query, projected)
                checked = query_answer_check(answer, references[query["id"]])
                if checked is False:
                    raise ValueError("Recovered query answer disagrees with journal-reconciled reference")
                report["checks"].append({"cell_id": index, "query_id": query["id"], "projection": projection["id"], "requested_unit": query["unit"], "requested_boundary": query["boundary"], **answer, "reference": references[query["id"]], "correct_answer": checked})
    report["unique_queries"] = len(cells) * len(QUERY_RECOVERY_PROTOCOL["queries"])
    report["projection_checks"] = len(report["checks"])
    report["summary"] = [{"projection": projection["id"], "queries": sum(row["projection"] == projection["id"] for row in report["checks"]), **{status: sum(row["projection"] == projection["id"] and row["status"] == status for row in report["checks"]) for status in ("recovered", "unknown", "undefined")}, "answered_correctly": sum(row["projection"] == projection["id"] and row["correct_answer"] is True for row in report["checks"]), "wrong_answers": sum(row["projection"] == projection["id"] and row["correct_answer"] is False for row in report["checks"])} for projection in QUERY_RECOVERY_PROTOCOL["projections"]]
    return report
