"""Validate v3 artifacts; --paired checks starts, --replay checks actions/outcomes.

Legacy aggregate-only pilots are deliberately rejected, not retroactively certified.
"""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised only in dependency-light installs.
    np = None

from .result_metrics import completed_outcomes


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_array(record):
    require(np is not None, "NumPy is required to validate hashed array records")
    a = np.asarray(record["values"], dtype=record["dtype"])
    require(a.dtype.kind in "fiu", "state/action array must be numeric")
    require(all(type(x) is int and x >= 0 for x in record["shape"]), "invalid array dimensions")
    require(list(a.shape) == record["shape"], "array shape mismatch")
    require(np.isfinite(a).all(), "nonfinite array")
    header = json.dumps([a.dtype.str, list(a.shape)], separators=(",", ":"))
    digest = hashlib.sha256(header.encode() + np.ascontiguousarray(a).tobytes()).hexdigest()
    require(digest == record["sha256"], "array hash mismatch")


def validate(data):
    d = data.get("robopad_ledger", data)
    version = d.get("schema_version")
    require(
        version in (2, 3),
        "v2 or v3 ledger required; legacy results lack completion/configuration evidence",
    )
    if version == 3:
        require(d.get("complete") is True, "run incomplete")
        require(
            all(
                d.get("contract", {}).get(k) for k in ("config", "checkpoint", "software", "source")
            ),
            "missing run contract",
        )
    require(d["episodes"], "no completed episodes")
    if "overall" in data and version == 3:
        require(
            data["overall"]["n_episodes"] == len(d["episodes"]), "completed episode count mismatch"
        )
    require(type(d["h"]) is int and d["h"] > 0, "invalid action prefix")
    require(type(d["denoising_steps"]) is int and d["denoising_steps"] > 0, "invalid solver steps")
    episodes = {}
    expected_chunks = 0
    for e in d["episodes"]:
        key = tuple(e["identity"])
        require(
            len(key) == 4
            and isinstance(key[0], str)
            and key[0]
            and all(type(x) is int and x >= 0 for x in key[1:]),
            "invalid episode identity",
        )
        if "suite" in d:
            require(d["suite"] == key[0], "episode/ledger suite mismatch")
        require(key not in episodes, "duplicate episode")
        episodes[key] = e
        if version == 3:
            require(e.get("complete") is True, "episode incomplete")
        require(set(e["seeds"]) == {"python", "numpy", "torch", "libero"}, "missing RNG seed")
        require(all(v == key[3] for v in e["seeds"].values()), "episode seed mismatch")
        check_array(e["initial_state"])
        producer, consumer = e["producer_steps"], e["environment_steps"]
        require(type(e["select_calls"]) is int, "selection count must be an integer")
        require(
            len(producer) == len(consumer) == e["select_calls"] > 0,
            "independent step counters disagree",
        )
        for i, (p, c) in enumerate(zip(producer, consumer)):
            require(
                type(p["step"]) is int and type(c["step"]) is int,
                "step identifiers must be integers",
            )
            require(p["step"] == c["step"] == i, "missing/duplicated/reordered step")
            check_array(p["action"])
            check_array(c["action"])
            require(
                p["action"]["sha256"] == c["action"]["sha256"],
                "producer/environment action mismatch",
            )
            if version == 3:
                require(
                    all(type(c.get(k)) is bool for k in ("terminated", "truncated", "success")),
                    "missing terminal evidence",
                )
                require(math.isfinite(c["reward"]), "invalid reward")
                if i < len(consumer) - 1:
                    require(not c["terminated"] and not c["truncated"], "steps after termination")
        if version == 3:
            require(len(consumer) <= e["max_steps"], "horizon exceeded")
            require(
                consumer[-1]["terminated"]
                or consumer[-1]["truncated"]
                or len(consumer) == e["max_steps"],
                "trajectory truncated before completion",
            )
            require(e["success"] == any(c["success"] for c in consumer), "episode success mismatch")
        events = [
            x for x in d["inferences"] if x["phase"] == "measured" and tuple(x["episode"]) == key
        ]
        require(
            [x["step"] for x in events] == list(range(0, len(consumer), d["h"])),
            "chunk schedule mismatch",
        )
        expected_chunks += len(events)
    for phase in ("warmup", "measured"):
        events = [x for x in d["inferences"] if x["phase"] == phase]
        require(
            all(
                type(d[name][phase]) is int and d[name][phase] >= 0
                for name in ("chunk_calls", "sampler_calls")
            ),
            "inference counters must be nonnegative integers",
        )
        require(
            all(type(x["step"]) is int and x["step"] >= 0 for x in events), "invalid inference step"
        )
        require(
            len(events) == d["chunk_calls"][phase] == d["sampler_calls"][phase],
            "independent sampler/chunk counters disagree",
        )
        require(
            all(math.isfinite(x["cuda_ms"]) and x["cuda_ms"] >= 0 for x in events),
            "invalid CUDA timing",
        )
    require(
        all(
            x["phase"] in ("warmup", "measured") and tuple(x["episode"]) in episodes
            for x in d["inferences"]
        ),
        "orphan inference",
    )
    warmup = [x for x in d["inferences"] if x["phase"] == "warmup"]
    require(
        type(d["warmup_passes"]) is int and d["warmup_passes"] == d["chunk_calls"]["warmup"] > 0,
        "warmup missing/mixed",
    )
    require(
        all(
            tuple(x["episode"]) == tuple(d["episodes"][0]["identity"]) and x["step"] == 0
            for x in warmup
        ),
        "warmup must precede first measured action",
    )
    require(
        all(x["phase"] == "warmup" for x in d["inferences"][: len(warmup)]),
        "warmup/measured events interleaved",
    )
    require(expected_chunks == d["chunk_calls"]["measured"], "unassigned measured chunks")
    if version == 3 and d["contract"].get("reference_check"):
        require(
            d["reference_steps"] == sum(len(e["environment_steps"]) for e in episodes.values()),
            "reference coverage incomplete",
        )
        require(d["reference_sampler_calls"] == expected_chunks, "reference sampler count mismatch")
    if "overall" in data and version == 3:
        expected = {}
        for e in d["episodes"]:
            expected.setdefault((e["identity"][0], e["identity"][1]), []).append(e["success"])
        actual = {
            (t["task_group"], t["task_id"]): t["metrics"]["successes"] for t in data["per_task"]
        }
        require(len(actual) == len(data["per_task"]), "duplicate task summaries")
        require(actual == expected, "reported task successes disagree with terminal trace")
        for task in data["per_task"]:
            matching = [
                e
                for e in d["episodes"]
                if (e["identity"][0], e["identity"][1]) == (task["task_group"], task["task_id"])
            ]
            for metric, reduce in (("sum_rewards", sum), ("max_rewards", max)):
                values = [reduce(row["reward"] for row in e["environment_steps"]) for e in matching]
                reported = task["metrics"].get(metric, [])
                require(
                    len(reported) == len(values)
                    and all(
                        math.isclose(x, y, rel_tol=1e-6, abs_tol=1e-6)
                        for x, y in zip(reported, values)
                    ),
                    "reported rewards disagree with trace",
                )
        rate = 100 * sum(e["success"] for e in d["episodes"]) / len(d["episodes"])
        require(math.isclose(data["overall"]["pc_success"], rate), "aggregate success mismatch")
    return d, episodes


def validate_completed(data):
    """Validate final evaluator output; a standalone ledger/journal is insufficient."""
    outcomes = completed_outcomes(data)
    d, episodes = validate(data)
    counts = {}
    for key in episodes:
        task = key[:2]
        counts[task] = counts.get(task, 0) + 1
    require(
        counts == {key: len(values) for key, values in outcomes.items()},
        "ledger/task outcome identities or counts disagree",
    )
    return d, episodes


def compare(left, right, replay=False):
    a, ea = validate(left)
    b, eb = validate(right)
    ca, cb = copy.deepcopy(a.get("contract", {})), copy.deepcopy(b.get("contract", {}))
    if not replay:
        for contract in (ca, cb):
            if "config" in contract:
                for field in ("n_action_steps", "num_steps"):
                    contract["config"].get("policy", {}).pop(field, None)
    require(ca == cb, "experimental contracts differ")
    require(ea.keys() == eb.keys(), "episode identities differ")
    for key in ea:
        require(
            ea[key]["initial_state"]["sha256"] == eb[key]["initial_state"]["sha256"],
            "initial states differ",
        )
        require(ea[key]["seeds"] == eb[key]["seeds"], "seed records differ")
        if replay:
            require(
                (a["h"], a["denoising_steps"]) == (b["h"], b["denoising_steps"]),
                "replay requires same condition",
            )
            require(
                ea[key]["environment_steps"] == eb[key]["environment_steps"],
                "action replay differs",
            )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ledger", type=Path)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--paired", type=Path)
    group.add_argument("--replay", type=Path)
    args = p.parse_args()
    data = json.loads(args.ledger.read_text())
    validate_completed(data)
    other = args.paired or args.replay
    if other:
        other_data = json.loads(other.read_text())
        validate_completed(other_data)
        compare(data, other_data, replay=bool(args.replay))
    print(
        "VALID v3 ledger"
        + (
            "; action/outcome replay verified"
            if args.replay
            else "; initial-state pairing verified"
            if args.paired
            else ""
        )
    )


if __name__ == "__main__":
    main()
