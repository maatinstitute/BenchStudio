#!/usr/bin/env python3
"""Reproduce the published aggregate and primary paired result."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchstudio.analysis import summarize_paired_outcomes

HERE = Path(__file__).resolve().parent


def load_records(path: Path = HERE / "confirmation_outcomes.jsonl") -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def reproduce() -> dict[str, Any]:
    records = load_records()
    expected = json.loads((HERE / "expected_summary.json").read_text(encoding="utf-8"))
    by_condition: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_condition[(record["h"], record["d"])].append(record)

    conditions = []
    for h, d in sorted(by_condition):
        group = by_condition[(h, d)]
        conditions.append(
            {
                "h": h,
                "d": d,
                "attempts": len(group),
                "successes": sum(record["success"] for record in group),
                "actions": sum(record["actions"] for record in group),
            }
        )

    selected = {record["block_id"]: record for record in by_condition[(2, 2)]}
    comparator = {record["block_id"]: record for record in by_condition[(2, 5)]}
    if selected.keys() != comparator.keys():
        raise ValueError("primary conditions do not contain identical paired blocks")
    block_ids = sorted(selected)
    paired = summarize_paired_outcomes(
        [comparator[block_id]["success"] for block_id in block_ids],
        [selected[block_id]["success"] for block_id in block_ids],
    )
    report = {
        "canonical_attempts": len(records),
        "recorded_actions": sum(record["actions"] for record in records),
        "conditions": conditions,
        "primary": {
            "paired_blocks": paired.matched_pairs,
            "selected_wins": paired.wins_b,
            "comparator_wins": paired.wins_a,
            "ties": paired.ties,
            "success_difference": paired.success_gap_b_minus_a,
            "benchstudio_exact_interval": list(paired.success_gap_confidence_interval or ()),
            "paper_descriptive_interval": expected["prespecified_primary_comparison"][
                "descriptive_interval"
            ],
        },
    }
    _check_expected(report, expected)
    return report


def _check_expected(report: dict[str, Any], expected: dict[str, Any]) -> None:
    study = expected["study"]
    if report["canonical_attempts"] != study["canonical_attempts"]:
        raise ValueError("canonical attempt count differs from the paper")
    if report["recorded_actions"] != study["recorded_actions"]:
        raise ValueError("recorded action count differs from the paper")
    if report["conditions"] != expected["conditions"]:
        raise ValueError("condition totals differ from the paper")
    primary = expected["prespecified_primary_comparison"]
    for field in (
        "paired_blocks",
        "selected_wins",
        "comparator_wins",
        "ties",
    ):
        if report["primary"][field] != primary[field]:
            raise ValueError(f"primary {field} differs from the paper")
    if not math.isclose(
        report["primary"]["success_difference"],
        primary["success_difference"],
        abs_tol=1e-12,
    ):
        raise ValueError("primary success_difference differs from the paper")


def main() -> int:
    print(json.dumps(reproduce(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
