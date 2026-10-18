"""Read two completed JSON annotation packets; report pre-adjudication agreement."""

import argparse
import json
from collections import Counter

DIMENSIONS = (
    "real_acquisition",
    "human_labor",
    "simulation",
    "wm_generation",
    "training_compute",
    "deployment_compute",
    "wall_time",
    "persistent_storage",
)
LABELS = ("Q", "P", "U", "NA")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def metrics(pairs):
    n = len(pairs)
    a, b = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    matrix = [[sum(x == i and y == j for x, y in pairs) for j in LABELS] for i in LABELS]
    observed = sum(x == y for x, y in pairs) / n if n else None
    expected = sum(a[k] * b[k] for k in LABELS) / n**2 if n else None
    kappa = (observed - expected) / (1 - expected) if n and expected < 1 else None
    return {
        "n": n,
        "raw_agreement": observed,
        "expected_agreement": expected,
        "kappa": kappa,
        "labels": LABELS,
        "confusion_A_rows_B_columns": matrix,
        "marginals_A": dict(a),
        "marginals_B": dict(b),
    }


def validate(packet):
    require(packet.get("codebook_version") == "1", "Codebook version mismatch")
    meta = packet["annotator"]
    require(meta.get("id") and meta.get("completed_at"), "Annotator identity/completion missing")
    require(meta.get("kind") in ("human", "model_assisted", "model"), "Annotator type missing")
    require(meta.get("prior_label_exposure") in ("none", "exposed"), "Exposure declaration missing")
    rows = packet["papers"]
    require(len(rows) == 16, "Expected 16 scoped papers")
    ids = set()
    for row in rows:
        require(row["system"] not in ids, "Duplicate system")
        ids.add(row["system"])
        require(
            all(
                row.get(k)
                for k in (
                    "citation",
                    "source_version",
                    "comparison_id",
                    "claim_locator",
                    "boundary",
                )
            ),
            "Freeze source and comparison scope first",
        )
        require(set(row["cells"]) == set(DIMENSIONS), "Expected exactly eight coordinates")
        for dim, c in row["cells"].items():
            require(c.get("label") in LABELS, f"Unresolved label: {row['system']}/{dim}")
            require(
                all(c.get(k) for k in ("source_locator", "evidence", "rationale")),
                "Evidence/locator/rationale missing",
            )
            if c["label"] == "Q":
                require(
                    all(c.get(k) for k in ("quantity", "unit", "denominator")),
                    "Q needs amount, unit and denominator",
                )
            if c["label"] == "U":
                require(c.get("search_log"), "U needs documented search")
    return {r["system"]: r for r in rows}


def compare(a, b):
    aa, bb = validate(a), validate(b)
    require(a["annotator"]["id"] != b["annotator"]["id"], "Two distinct annotator IDs required")
    require(aa.keys() == bb.keys(), "Corpora differ")
    pairs, by_dim, disagreements = [], {d: [] for d in DIMENSIONS}, []
    for system in sorted(aa):
        ra, rb = aa[system], bb[system]
        require(
            all(
                ra[k] == rb[k]
                for k in (
                    "citation",
                    "source_version",
                    "comparison_id",
                    "claim_locator",
                    "boundary",
                )
            ),
            f"Scope/source mismatch: {system}",
        )
        for dim in DIMENSIONS:
            x, y = ra["cells"][dim]["label"], rb["cells"][dim]["label"]
            pairs.append((x, y))
            by_dim[dim].append((x, y))
            if x != y:
                disagreements.append(
                    {
                        "system": system,
                        "dimension": dim,
                        "A": ra["cells"][dim],
                        "B": rb["cells"][dim],
                        "adjudicated_label": None,
                        "adjudication_rationale": None,
                        "adjudication_locator": None,
                        "adjudicator": None,
                        "date": None,
                    }
                )
    return {
        "status": "pre_adjudication",
        "annotators": [a["annotator"], b["annotator"]],
        "independence": "self-declared; not verified by this program",
        "overall": metrics(pairs),
        "per_dimension": {d: metrics(v) for d, v in by_dim.items()},
        "both_applicable_sensitivity": metrics(
            [(x, y) for x, y in pairs if x != "NA" and y != "NA"]
        ),
        "disagreements": disagreements,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotator_a")
    parser.add_argument("annotator_b")
    args = parser.parse_args()
    with open(args.annotator_a) as fa, open(args.annotator_b) as fb:
        print(json.dumps(compare(json.load(fa), json.load(fb)), indent=2, allow_nan=False))
