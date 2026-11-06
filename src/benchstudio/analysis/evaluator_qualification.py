"""Policy-free qualification of a native evaluator against independent goal checks."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

SCHEMA = "benchstudio.evaluator_qualification.v1"
_REQUIRED = {"goal_reached", "goal_unmet", "horizon_timeout"}
_OPTIONAL = {"non_goal_termination"}
_STOP_REASONS = {"goal", "horizon", "other"}


def _sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _state_sha256(state: dict[str, Any]) -> str:
    data = json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def build_evaluator_report(
    *,
    model: str,
    runtime: dict[str, str],
    goal_checker_sha256: str,
    fixtures: Iterable[dict[str, Any]],
    check_goal: Callable[[str, str, str, dict[str, Any]], bool],
) -> dict[str, Any]:
    """Check native, policy-free traces using a separate goal checker.

    The callback receives suite, task ID, goal definition hash, and a JSON
    snapshot. The native evaluator supplies its own success and stop signals.
    Keep the raw snapshots and checker source with the qualification evidence.
    """
    cases = []
    for fixture in fixtures:
        case = {key: fixture[key] for key in (
            "suite", "task_id", "kind", "horizon", "goal_spec_sha256", "recorded_success"
        )}
        samples = []
        for sample in fixture["samples"]:
            state = sample["state"]
            if not isinstance(state, dict) or not state:
                raise ValueError("each fixture sample needs a nonempty state snapshot")
            digest = _state_sha256(state)
            # Isolate the snapshot from any changes made by the checker.
            snapshot = json.loads(json.dumps(state, allow_nan=False))
            goal = check_goal(case["suite"], case["task_id"], case["goal_spec_sha256"], snapshot)
            samples.append({
                "step": sample["step"],
                "state_sha256": digest,
                "goal_met": goal,
                "native_success": sample["native_success"],
                "stop_reason": sample["stop_reason"],
            })
        case["samples"] = samples
        cases.append(case)
    report = {
        "schema": SCHEMA,
        "model": model,
        "runtime": dict(runtime),
        "goal_checker_sha256": goal_checker_sha256,
        "cases": cases,
    }
    horizons = {case["suite"]: case["horizon"] for case in cases}
    issues = evaluator_issues(report, model=model, runtime=runtime, horizons=horizons)
    return {**report, "passed": not issues, "issues": issues}


def evaluator_issues(
    report: Mapping[str, Any],
    *,
    model: str,
    runtime: Mapping[str, str],
    horizons: Mapping[str, int],
) -> list[str]:
    """Recompute coverage and semantic checks at launch from the recorded evidence."""
    issues: list[str] = []
    if report.get("schema") != SCHEMA or report.get("model") != model:
        issues.append("evaluator schema or model mismatch")
    if report.get("runtime") != runtime:
        issues.append("evaluator runtime mismatch")
    checker = report.get("goal_checker_sha256")
    if not _sha(checker) or checker == runtime.get("runner"):
        issues.append("separate goal checker identity is required")
    cases = report.get("cases")
    if not isinstance(cases, list):
        return [*issues, "evaluator cases must be a list"]
    seen: dict[str, set[str]] = {suite: set() for suite in horizons}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            issues.append(f"case {index}: must be an object")
            continue
        suite, kind = case.get("suite"), case.get("kind")
        if not isinstance(suite, str) or suite not in seen:
            issues.append(f"case {index}: unexpected suite")
            continue
        if not isinstance(kind, str) or kind not in _REQUIRED | _OPTIONAL:
            issues.append(f"case {index}: unknown kind")
            continue
        if kind in seen[suite]:
            issues.append(f"{suite}/{kind}: duplicate case")
            continue
        seen[suite].add(kind)
        horizon = case.get("horizon")
        if horizon != horizons[suite]:
            issues.append(f"{suite}/{kind}: horizon does not match the declared suite horizon")
        issues.extend(f"{suite}/{kind}: {issue}" for issue in _case_issues(case, kind, horizon))
    if not horizons:
        issues.append("no evaluator suites declared")
    for suite, covered in sorted(seen.items()):
        if missing := _REQUIRED - covered:
            issues.append(f"{suite}: missing cases {', '.join(sorted(missing))}")
    return issues


def _case_issues(case: dict[str, Any], kind: str, horizon: object) -> list[str]:
    if type(horizon) is not int or horizon < 1:
        return ["horizon must be a positive integer"]
    if not isinstance(case.get("task_id"), str) or not case["task_id"].strip():
        return ["task ID is required"]
    if not _sha(case.get("goal_spec_sha256")):
        return ["goal definition digest is required"]
    samples = case.get("samples")
    if not isinstance(samples, list) or not 1 <= len(samples) <= horizon + 1:
        return ["expected an uninterrupted trace within the horizon"]

    for step, sample in enumerate(samples):
        if (
            not isinstance(sample, dict)
            or type(sample.get("step")) is not int
            or sample["step"] != step
            or not _sha(sample.get("state_sha256"))
            or type(sample.get("goal_met")) is not bool
            or type(sample.get("native_success")) is not bool
            or "stop_reason" not in sample
        ):
            return [f"invalid evidence at step {step}"]
        reason = sample["stop_reason"]
        if reason is not None and (
            not isinstance(reason, str) or reason not in _STOP_REASONS or step != len(samples) - 1
        ):
            return [f"invalid stop reason at step {step}"]
        if sample["native_success"] != sample["goal_met"]:
            return [f"native success disagrees with independent goal at step {step}"]

    initial, final = samples[0], samples[-1]
    reached = any(sample["goal_met"] for sample in samples)
    reason = final["stop_reason"]
    recorded = case.get("recorded_success")
    if kind == "goal_unmet":
        return [] if (
            len(samples) == 1 and not reached and reason is None
            and "recorded_success" in case and recorded is None
        ) else ["expected a negative reset probe with no episode outcome"]
    if type(recorded) is not bool or recorded != reached:
        return ["recorded episode success disagrees with independent first attainment"]
    if initial["goal_met"] or len(samples) < 2 or reason is None:
        return ["expected a negative reset followed by a terminal episode"]
    if reason == "horizon" and final["step"] != horizon:
        return ["horizon stop did not occur at the declared step"]
    if reason == "goal" and not final["goal_met"]:
        return ["goal termination without a satisfied terminal goal"]
    if kind == "goal_reached" and not reached:
        return ["positive fixture never reached the goal"]
    if kind == "horizon_timeout" and (reached or reason != "horizon"):
        return ["expected a goal-unmet episode ending at the horizon"]
    if kind == "non_goal_termination" and (reached or reason != "other" or final["step"] >= horizon):
        return ["expected a goal-unmet termination before the horizon"]
    return []
