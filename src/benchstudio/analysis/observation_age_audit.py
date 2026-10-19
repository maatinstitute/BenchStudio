#!/usr/bin/env python3
"""Validate retained observation-age runs and report first replay divergences."""

import argparse
import hashlib
import json
from pathlib import Path

def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
        ).encode()
    ).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def journal(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def identity(row):
    e = row["episode_identity"]
    return (e["suite"], e["task_id"], e["initial_state_id"], e["policy_seed"])


def validate_inputs(steps, refresh):
    held = fields = None
    for tick, event in enumerate(steps):
        require(event["tick"] == tick, "input tick sequence differs")
        updated = tick % refresh == 0
        require(
            type(event["input_refreshed"]) is bool and event["input_refreshed"] == updated,
            "input refresh differs",
        )
        require(
            event["supplied_observation_tick"] == tick - tick % refresh
            and event["supplied_observation_age_ticks"] == tick % refresh,
            "input age differs",
        )
        current = event["current_observation_sha256"]
        supplied = event["supplied_observation_sha256"]
        require(
            all(
                isinstance(h, str) and len(h) == 64 and all(c in "0123456789abcdef" for c in h)
                for h in (current, supplied)
            ),
            "invalid input digest",
        )
        if updated:
            require(current == supplied, "refresh input differs from current observation")
            held, fields = supplied, event["supplied_observation_field_sha256"]
        require(
            supplied == held and event["supplied_observation_field_sha256"] == fields,
            "held input changed before refresh",
        )
        # observation_sha recursively hashes arrays, then hashes the resulting tree.
        require(
            digest(event["supplied_observation_field_sha256"]) == supplied,
            "input field hashes do not reconcile",
        )
    # Current and held observations may legitimately be equal in a static scene.


def validate_run(root, instrumented):
    import numpy as np

    rows = journal(root / "episodes.jsonl")
    events = journal(root / "steps.jsonl")
    manifest, summary = read(root / "runtime_manifest.json"), read(root / "summary.json")
    schedule = read(root / "selected_schedule.json")
    require(summary["status"] == "completed", "run is incomplete")
    require(
        summary["episodes"] == rows
        and len(rows) == 40
        and summary["completed_attempts"] == summary["expected_attempts"] == 40,
        "summary/coverage differs",
    )
    require(
        schedule == manifest["selected_schedule"]
        and digest(schedule) == manifest["selected_schedule_sha256"] == summary["schedule_sha256"],
        "schedule digest differs",
    )
    require(digest(manifest) == summary["runtime_manifest_sha256"], "manifest digest differs")
    require(
        [r["planned_run_id"] for r in rows] == [r["planned_run_id"] for r in schedule],
        "schedule order differs",
    )
    require(len({identity(r) for r in rows}) == 40, "duplicate identities")
    expected = {
        ("libero_spatial", t, s, seed)
        for t in range(5, 9)
        for s in range(10, 15)
        for seed in (2000, 2001)
    }
    require({identity(r) for r in rows} == expected, "unexpected task/state/seed coverage")
    cursor, streams = 0, {}
    for row, planned in zip(rows, schedule):
        require(
            row["h"] == planned["h"] == 1
            and row["denoising_steps"] == planned["denoising_steps"] == 5,
            "diagnostic setting differs",
        )
        require(row["episode_identity"] == planned["episode_identity"], "identity differs")
        require(row["runtime_manifest_sha256"] == digest(manifest), "episode manifest differs")
        start = events[cursor]
        require(
            start["kind"] == "episode_start"
            and start["run_id"] == row["run_id"]
            and start["initial_state"] == row["initial_state"]
            and start["initial_observation_sha256"] == row["initial_observation_sha256"],
            "episode start differs",
        )
        n = row["steps"]
        steps = events[cursor + 1 : cursor + n + 1]
        require(len(steps) == n and 0 < n <= row["task_horizon"], "invalid episode length")
        for tick, e in enumerate(steps):
            require(
                e["kind"] == "step" and e["tick"] == tick and e["run_id"] == row["run_id"],
                "action sequence differs",
            )
            require(
                e["new_generation"] is True
                and e["action_age_ticks"] == 0
                and e["generation_origin_tick"] == tick,
                "generation schedule differs",
            )
            seed = int.from_bytes(
                bytes.fromhex(digest(["policy_noise", row["episode_identity"], tick]))[:4], "little"
            )
            require(e["noise_seed"] == seed, "noise seed differs")
            a = e["producer_action"]
            values = np.asarray(a["values"], dtype=a["dtype"])
            header = json.dumps([a["dtype"], a["shape"]], separators=(",", ":")).encode()
            require(
                list(values.shape) == a["shape"] == [7] and np.isfinite(values).all(),
                "invalid action values",
            )
            require(
                hashlib.sha256(header + values.tobytes()).hexdigest()
                == a["sha256"]
                == e["environment_action_sha256"],
                "action digest differs",
            )
            require(
                e["driver_is_success"] == e["vector_is_success"]
                and e["driver_terminated"] == e["vector_terminated"],
                "outcome interfaces differ",
            )
        require(
            digest([e["producer_action"]["sha256"] for e in steps]) == row["action_stream_sha256"],
            "action stream digest differs",
        )
        require(
            any(e["vector_is_success"] for e in steps)
            == row["success"]
            == row["independent_driver"]["success"],
            "episode outcome differs",
        )
        require(
            row["counts"]
            == dict(
                generations=n,
                denoise_steps=5 * n,
                vision_encoder_calls=2 * n,
                prefill_calls=n,
                action_expert_calls=5 * n,
            ),
            "work counts differ",
        )
        end = events[cursor + n + 1]
        require(
            end
            == dict(
                kind="episode_completed",
                run_id=row["run_id"],
                success=row["success"],
                steps=n,
                action_stream_sha256=row["action_stream_sha256"],
            ),
            "episode end differs",
        )
        if instrumented:
            validate_inputs(steps, manifest["argv"]["observation_refresh"])
            require(
                steps[0]["current_observation_sha256"] == row["initial_observation_sha256"],
                "initial input hash differs",
            )
        streams[identity(row)] = steps
        cursor += n + 2
    require(cursor == len(events), "unaccounted journal events")
    require(
        sum(r["success"] for r in rows) == summary["aggregate_successes"], "success total differs"
    )
    return rows, manifest, streams


def analyze(root, fresh=None):
    import numpy as np

    old, oldm, olds = validate_run(root / "stale", False)
    new, newm, news = validate_run(root / "stale_instrumented_004", True)
    original = {identity(r): r for r in old}
    divergences = []
    for r in new:
        k, a = identity(r), original[identity(r)]
        require(
            a["initial_state"]["sha256"] == r["initial_state"]["sha256"]
            and a["initial_observation_sha256"] == r["initial_observation_sha256"],
            "reset pairing differs",
        )
        for x, y in zip(olds[k], news[k]):
            if x["producer_action"]["sha256"] != y["producer_action"]["sha256"]:
                av, bv = (
                    np.asarray(x["producer_action"]["values"]),
                    np.asarray(y["producer_action"]["values"]),
                )
                divergences.append(
                    dict(
                        identity=k,
                        first_tick=x["tick"],
                        first_action_max_abs_difference=float(np.max(np.abs(av - bv))),
                        old_steps=a["steps"],
                        new_steps=r["steps"],
                    )
                )
                break
    report = dict(
        attempts=40,
        historical_successes=sum(r["success"] for r in old),
        instrumented_successes=sum(r["success"] for r in new),
        historical_steps=sum(r["steps"] for r in old),
        instrumented_steps=sum(r["steps"] for r in new),
        divergent_streams=divergences,
        environment_changes={
            k: [oldm["execution_environment"].get(k), newm["execution_environment"].get(k)]
            for k in oldm["execution_environment"]
            if oldm["execution_environment"].get(k) != newm["execution_environment"].get(k)
        },
        interpretation=(
            "Repeated evaluation of the same identities; runtime differences remain "
            "confounded with instrumentation."
        ),
    )
    if fresh:
        fr, fm, _ = validate_run(fresh, True)
        require(fm["argv"]["observation_refresh"] == 1, "control is not fresh input")
        for key in (
            "checkpoint_files_sha256",
            "verified_pinned_source_sha256",
            "control",
            "precision",
            "execution_environment",
            "source_sha256",
        ):
            require(fm[key] == newm[key], f"matched-control runtime differs: {key}")
        stale = {identity(r): r for r in new}
        for r in fr:
            require(
                r["initial_state"]["sha256"] == stale[identity(r)]["initial_state"]["sha256"]
                and r["initial_observation_sha256"]
                == stale[identity(r)]["initial_observation_sha256"],
                "fresh/stale pairing differs",
            )
        report["fresh_control"] = dict(
            successes=sum(r["success"] for r in fr),
            attempts=len(fr),
            stale_minus_fresh_points=100
            * np.mean([int(stale[identity(r)]["success"]) - int(r["success"]) for r in fr]),
            note=(
                "Same discovery identities; analysis specified after historical stale "
                "outcomes were observed."
            ),
        )
    report["input_sha256"] = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for name in ("stale", "stale_instrumented_004")
        for p in sorted((root / name).iterdir())
        if p.is_file()
    }
    if fresh:
        report["fresh_input_sha256"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(fresh.iterdir())
            if p.is_file()
        }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--fresh", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.root, args.fresh)
    rendered = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered)
