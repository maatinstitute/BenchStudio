"""Conservative paired accounting for the outcome-conditioning campaign."""

from __future__ import annotations

import math
from typing import Any, Iterable


def _binomial_cdf(k: int, n: int, probability: float) -> float:
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return math.fsum(
        math.comb(n, j) * probability**j * (1 - probability) ** (n - j) for j in range(k + 1)
    )


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Return an exact two-sided binomial interval by beta-quantile inversion."""
    if type(k) is not int or type(n) is not int or not 0 <= k <= n or n <= 0:
        raise ValueError("expected 0 <= k <= n with positive n")
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie in (0, 1)")
    tail = alpha / 2
    low = 0.0
    if k:
        left, right = 0.0, 1.0
        for _ in range(100):
            middle = (left + right) / 2
            if 1.0 - _binomial_cdf(k - 1, n, middle) > tail:
                right = middle
            else:
                left = middle
        low = (left + right) / 2
    high = 1.0
    if k != n:
        left, right = 0.0, 1.0
        for _ in range(100):
            middle = (left + right) / 2
            if _binomial_cdf(k, n, middle) > tail:
                left = middle
            else:
                right = middle
        high = (left + right) / 2
    return low, high


def discordance_interval(
    wins: int, losses: int, n: int, alpha: float = 0.05
) -> tuple[float, float]:
    if type(wins) is not int or type(losses) is not int or type(n) is not int:
        raise ValueError("discordance counts must be integers")
    if wins < 0 or losses < 0 or n <= 0 or wins + losses > n:
        raise ValueError("invalid discordance counts")
    win_low, win_high = clopper_pearson(wins, n, alpha)
    loss_low, loss_high = clopper_pearson(losses, n, alpha)
    return win_low - loss_high, win_high - loss_low


def summarize_cells(
    planned: Iterable[dict[str, Any]], receipts: Iterable[dict[str, Any]]
) -> dict[str, int]:
    planned_ids = [row["cell_id"] for row in planned]
    receipt_rows = list(receipts)
    if len(set(planned_ids)) != len(planned_ids):
        raise ValueError("planned cell IDs must be unique")
    seen = set()
    for receipt in receipt_rows:
        if receipt.get("cell_id") in seen:
            raise ValueError("duplicate receipt cell")
        seen.add(receipt.get("cell_id"))
        if receipt.get("cell_id") not in set(planned_ids):
            raise ValueError("receipt is outside planned matrix")
    statuses = {
        status: sum(row.get("status") == status for row in receipt_rows)
        for status in ("complete", "excluded", "failed", "partial")
    }
    return {
        "planned": len(planned_ids),
        "attempted": len(receipt_rows),
        "complete": statuses["complete"],
        "excluded": statuses["excluded"],
        "failed": statuses["failed"],
        "partial": statuses["partial"],
        "missing": len(planned_ids) - len(receipt_rows),
    }


def analyze_primary(
    cells: Iterable[dict[str, Any]],
    *,
    planned: Iterable[dict[str, Any]],
    tasks: int = 6,
    seeds: tuple[int, ...] = (123, 456, 789, 1011, 1213),
    alpha: float = 0.05,
) -> dict[str, Any]:
    rows = list(cells)
    planned_rows = list(planned)
    if tasks <= 0 or not seeds:
        raise ValueError("primary analysis requires tasks and seeds")
    if len(set(seeds)) != len(seeds):
        raise ValueError("primary analysis seeds must be unique")
    if not planned_rows:
        return {
            "task_count": tasks,
            "seed_count": len(seeds),
            "planned_cells": 0,
            "observed_cells": 0,
            "parents": 0,
            "missing_groups": tasks * len(seeds),
            "missing_group_keys": [[task, seed] for task in range(1, tasks + 1) for seed in seeds],
            "missing_cells": [],
            "interval_method": "simultaneous_clopper_pearson_discordance_v1",
            "status": "partial_missing",
            "interval": None,
            "missingness_bounds": [-1.0, 1.0],
        }
    planned_keys: set[tuple[int, int, Any]] = set()
    for row in planned_rows:
        key = (row.get("task_id"), row.get("seed"), row.get("parent_id"))
        if None in key:
            raise ValueError("planned primary cells require task, seed and parent identities")
        if key[0] not in range(1, tasks + 1):
            raise ValueError("planned primary task is outside the frozen domain")
        if key[1] not in seeds:
            raise ValueError("planned primary seed is outside the frozen domain")
        if key in planned_keys:
            raise ValueError("planned primary cells must be unique")
        planned_keys.add(key)
    panels: dict[int, dict[int, set[Any]]] = {}
    for task, seed, parent in planned_keys:
        panels.setdefault(task, {}).setdefault(seed, set()).add(parent)
    for task, seed_panels in panels.items():
        if len({frozenset(panel) for panel in seed_panels.values()}) > 1:
            raise ValueError("planned parent panel differs across seeds")
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    parent_keys: set[tuple[int, int, str]] = set()
    observed_keys: set[tuple[int, int, Any]] = set()
    for row in rows:
        key = (row.get("task_id"), row.get("seed"))
        parent = row.get("parent_id")
        parent_key = (*key, parent)
        observed_key = (*parent_key,)
        if observed_key not in planned_keys:
            raise ValueError("observed primary cell is outside the frozen planned matrix")
        if parent_key in parent_keys:
            raise ValueError("duplicate parent")
        parent_keys.add(parent_key)
        observed_keys.add(observed_key)
        grouped.setdefault(key, []).append(row)
        if row.get("status") != "complete":
            raise ValueError("primary analysis accepts complete cells only")
        if type(row.get("c_success")) is not bool or type(row.get("u_success")) is not bool:
            raise ValueError("primary analysis requires boolean outcomes")
    expected = [(task, seed) for task in range(1, tasks + 1) for seed in seeds]
    missing = [key for key in expected if key not in grouped or not grouped[key]]
    missing_cells = sorted(
        planned_keys - observed_keys, key=lambda key: tuple(str(value) for value in key)
    )
    result: dict[str, Any] = {
        "task_count": tasks,
        "seed_count": len(seeds),
        "planned_cells": len(planned_keys),
        "observed_cells": len(observed_keys),
        "parents": len({(task, parent) for task, _seed, parent in planned_keys}),
        "missing_groups": len(missing),
        "missing_group_keys": [list(key) for key in missing],
        "missing_cells": [list(key) for key in missing_cells],
        "interval_method": "simultaneous_clopper_pearson_discordance_v1",
    }
    if not planned_keys or missing or missing_cells:
        observed_difference = sum(
            (
                1
                if row["c_success"] and not row["u_success"]
                else -1
                if row["u_success"] and not row["c_success"]
                else 0
            )
            for row in rows
        )
        total_cells = len(planned_keys)
        missing_count = len(missing_cells)
        lower = (observed_difference - missing_count) / total_cells if total_cells else -1.0
        upper = (observed_difference + missing_count) / total_cells if total_cells else 1.0
        result.update(
            status="partial_missing",
            interval=None,
            missingness_bounds=[max(-1.0, lower), min(1.0, upper)],
        )
        return result
    group_results = []
    per_group_alpha = alpha / (2 * tasks * len(seeds))
    for key in expected:
        group = grouped[key]
        wins = sum(row["c_success"] and not row["u_success"] for row in group)
        losses = sum(row["u_success"] and not row["c_success"] for row in group)
        interval = discordance_interval(wins, losses, len(group), per_group_alpha)
        group_results.append(
            {
                "task_id": key[0],
                "seed": key[1],
                "n": len(group),
                "wins": wins,
                "losses": losses,
                "difference": (wins - losses) / len(group),
                "interval": list(interval),
            }
        )
    lower = sum(group["interval"][0] for group in group_results) / len(group_results)
    upper = sum(group["interval"][1] for group in group_results) / len(group_results)
    point = sum(group["difference"] for group in group_results) / len(group_results)
    result.update(
        status="complete", point_estimate=point, interval=[lower, upper], groups=group_results
    )
    return result
