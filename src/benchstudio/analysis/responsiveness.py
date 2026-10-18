"""RoboPAD source-backed selective-responsiveness analysis.

The metric separates the question ``should the policy change?`` from whether
the resulting behavior is correct. Inputs are independently judged,
episode-grouped records; missing classes remain undefined rather than being
treated as zero or one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from typing import Any, Iterable


def split_for(episode_id: str) -> str:
    bucket = int(hashlib.sha256(("proposal1-v1:" + episode_id).encode()).hexdigest()[:8], 16) % 10
    return "train" if bucket < 6 else ("validation" if bucket < 8 else "test")


def validate(rows: Iterable[dict[str, Any]]) -> None:
    ids: set[str] = set()
    splits: dict[str, Any] = {}
    for row in rows:
        pair_id = row["pair_id"]
        if pair_id in ids:
            raise ValueError("Duplicate pair_id")
        ids.add(pair_id)
        for key in ["should_change", "appropriate_change", "stable", "correct_0", "correct_1"]:
            if type(row.get(key)) is not bool:
                raise ValueError(f"{key} must be an independently judged boolean")
        if row.get("oracle_status") != "validated" or not row.get("oracle_evidence"):
            raise ValueError("Validated oracle evidence is required")
        episode = row["episode_id"]
        if episode in splits and splits[episode] != row["split"]:
            raise ValueError("Episode leakage across splits")
        splits[episode] = row["split"]
    if len(set(splits.values())) > 1:
        raise ValueError("Report each split separately")


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    relevant = [row for row in rows if row["should_change"]]
    irrelevant = [row for row in rows if not row["should_change"]]
    tpr = (
        sum(row["appropriate_change"] and row["correct_0"] and row["correct_1"] for row in relevant)
        / len(relevant)
        if relevant
        else None
    )
    tnr = sum(row["stable"] for row in irrelevant) / len(irrelevant) if irrelevant else None
    scr = (
        None if tpr is None or tnr is None else (2 * tpr * tnr / (tpr + tnr) if tpr + tnr else 0.0)
    )
    return {
        "n_pairs": len(rows),
        "n_react": len(relevant),
        "n_stable": len(irrelevant),
        "tpr_react": tpr,
        "tnr_stable": tnr,
        "scr": scr,
        "paired_correctness": (
            sum(row["correct_0"] and row["correct_1"] for row in rows) / len(rows) if rows else None
        ),
    }


def summarize(rows: list[dict[str, Any]], draws: int = 2000, seed: int = 123) -> dict[str, Any]:
    validate(rows)
    result = score(rows)
    groups = defaultdict(list)
    for row in rows:
        groups[row["episode_id"]].append(row)
    result["n_episodes"] = len(groups)
    result["bootstrap_unit"] = "episode"
    result["intervals_95"] = {}
    if len(groups) < 2:
        return result
    rng = random.Random(seed)
    group_values = list(groups.values())
    samples = [
        score([row for group in rng.choices(group_values, k=len(group_values)) for row in group])
        for _ in range(draws)
    ]
    for key in ["tpr_react", "tnr_stable", "scr", "paired_correctness"]:
        values = sorted(sample[key] for sample in samples if sample[key] is not None)
        result["intervals_95"][key] = {
            "valid_draws": len(values),
            "total_draws": draws,
            "percentile": (
                [values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]]
                if values
                else None
            ),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("records")
    args = parser.parse_args()
    with open(args.records, encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    print(json.dumps(summarize(rows), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
