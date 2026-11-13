"""Reconcile completed evaluator results before computing descriptive summaries.

No success confidence intervals are emitted: the archived pilot uses selected
tasks and repeated/overlapping episodes, not an independent benchmark sample.
"""

import math


def require(condition, message):
    if not condition:
        raise ValueError(message)


def completed_outcomes(data):
    require("overall" in data and "per_task" in data, "completed eval_info result required")
    overall = data["overall"]
    outcomes = {}
    for task in data["per_task"]:
        key = (task["task_group"], task["task_id"])
        require(
            isinstance(key[0], str) and key[0] and type(key[1]) is int and key[1] >= 0,
            "invalid task identity",
        )
        require(key not in outcomes, "duplicate task metrics")
        successes = task["metrics"]["successes"]
        require(isinstance(successes, list) and successes, "missing task outcomes")
        require(all(type(x) is bool for x in successes), "success outcomes must be booleans")
        outcomes[key] = successes
    n = sum(len(x) for x in outcomes.values())
    wins = sum(sum(x) for x in outcomes.values())
    require(
        n > 0 and type(overall["n_episodes"]) is int and n == overall["n_episodes"],
        "outcome/overall episode counts disagree",
    )
    require(
        math.isclose(overall["pc_success"], 100 * wins / n, abs_tol=1e-8),
        "outcome/overall success rates disagree",
    )
    require(math.isfinite(overall["eval_s"]) and overall["eval_s"] >= 0, "invalid rollout timing")
    if "per_group" in data:
        groups = {key[0] for key in outcomes}
        require(set(data["per_group"]) == groups, "task/group keys disagree")
        for group, metrics in data["per_group"].items():
            values = [x for key, xs in outcomes.items() if key[0] == group for x in xs]
            require(metrics["n_episodes"] == len(values), "task/group episode counts disagree")
            require(
                math.isclose(metrics["pc_success"], 100 * sum(values) / len(values), abs_tol=1e-8),
                "task/group success rates disagree",
            )
    return outcomes


def summarize(data):
    outcomes = completed_outcomes(data)
    ledger = data["robopad_ledger"]
    version = ledger.get("schema_version", 1)
    legacy_host_seconds = None
    if version in (2, 3):
        from validate_ledger import validate_completed

        validate_completed(data)
        controls = sum(e["select_calls"] for e in ledger["episodes"])
        chunks = ledger["chunk_calls"]["measured"]
        timing = "CUDA-event stream elapsed; warmup excluded from inference events"
    else:
        require(version == 1, "unsupported ledger version")
        controls, chunks = ledger["select_action_calls"], ledger["neural_chunk_calls"]
        times = ledger["neural_chunk_seconds"]
        require(len(times) == chunks, "legacy timing/chunk counts disagree")
        require(all(math.isfinite(x) and x >= 0 for x in times), "invalid legacy timing")
        legacy_host_seconds = math.fsum(times)
        timing = "host elapsed with post-call CUDA synchronization; includes cold calls"
    require(
        type(controls) is int and type(chunks) is int and controls >= chunks > 0,
        "invalid control/chunk counts",
    )
    values = [x for xs in outcomes.values() for x in xs]
    return {
        "ledger_version": version,
        "successes": sum(values),
        "episodes": len(values),
        "success_rate_percent": 100 * sum(values) / len(values),
        "control_steps": controls,
        "neural_chunks": chunks,
        "control_to_neural": controls / chunks,
        "rollout_seconds": data["overall"]["eval_s"],
        "legacy_inference_host_seconds": legacy_host_seconds,
        "timing_scope": timing,
        "pairing_evidence": "available for explicit comparison" if version == 2 else "unverifiable",
    }
