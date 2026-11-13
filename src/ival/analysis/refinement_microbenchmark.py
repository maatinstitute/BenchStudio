"""Dependency-free validation of Refinement/Refresh inference microbenchmarks."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .refinement_rollout_audit import require


def valid_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def file_sha(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def positive_number(value: Any, allow_zero: bool = False) -> bool:
    return type(value) in (float, int) and math.isfinite(value) and (value >= 0 if allow_zero else value > 0)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_microbenchmark(root: str | Path, completion: dict[str, Any]) -> list[dict[str, Any]]:
    """Reconcile paired predictions before reducing timing or overhead data."""
    root_path = Path(root)
    require(completion.get("status") == "complete", "Microbenchmark must be complete before analysis")
    config = completion.get("config", {})
    blocks, calls, warmup = (config.get(key) for key in ("blocks", "calls", "warmup_calls"))
    require(type(blocks) is int and blocks > 0 and type(calls) is int and calls > 0 and type(warmup) is int and warmup >= 0, "Missing/invalid declared microbenchmark allocation")
    solvers = config.get("num_steps")
    require(isinstance(solvers, list) and solvers and all(type(value) is int and value > 0 for value in solvers) and len(set(solvers)) == len(solvers), "Invalid declared solver settings")
    expected = {(block, solver, phase, index) for block in range(blocks) for solver in solvers for phase, count in (("warmup", warmup), ("measurement", calls)) for index in range(count)}
    pairs = read_jsonl(root_path / "pairs.jsonl")
    keyed: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in pairs:
        key = tuple(row.get(field) for field in ("block", "num_steps", "phase", "call_index"))
        require(key in expected and key not in keyed, "Unexpected/duplicate inference pair")
        require(row.get("pair_id") == f"b{key[0]}:d{key[1]}:{key[2]}:{key[3]}", "Inference pair ID mismatch")
        require(type(row.get("allclose")) is bool and row["allclose"], "Instrumented prediction parity failed or missing")
        require(type(row.get("exact_equal")) is bool, "Invalid exact-parity flag")
        require(all(valid_hash(row.get(f"{mode}_action_sha256")) for mode in ("off", "on")), "Missing action hashes for instrumentation pair")
        require(row["exact_equal"] == (row["off_action_sha256"] == row["on_action_sha256"]), "Exact-parity flag disagrees with action hashes")
        require(positive_number(row.get("max_abs_diff"), True), "Invalid recorded action difference")
        require(not row["exact_equal"] or row["max_abs_diff"] == 0, "Exact outputs have nonzero difference")
        for mode in ("off", "on"):
            require(positive_number(row.get(f"{mode}_host_elapsed_ms")), "Invalid host prediction timing")
            require(positive_number(row.get(f"{mode}_cuda_elapsed_ms"), True), "Invalid CUDA prediction timing")
        for tolerance in ("rtol", "atol"):
            require(positive_number(row.get(tolerance), True) and row[tolerance] == config.get(tolerance), "Pair tolerance differs from declared configuration")
        keyed[key] = row
    require(set(keyed) == expected, "Missing declared solver/block/measurement pair")
    counts = completion.get("counts", {})
    expected_counts = {"completed_actual_chunk_generations": len(expected) * 2, "issued_prediction_calls": len(expected) * 2, "completed_pairs": len(expected), "unpaired_calls": 0, "measured_calls": blocks * len(solvers) * calls * 2, "warmup_calls": blocks * len(solvers) * warmup * 2, "pairs_allclose": len(expected), "pairs_exact_equal": sum(row["exact_equal"] for row in pairs)}
    require(all(type(counts.get(key)) is int and counts[key] == value for key, value in expected_counts.items()), "Microbenchmark summary counts disagree with declared pairs")
    require(completion.get("planned_actual_chunk_generations") == len(expected) * 2, "Microbenchmark planned allocation disagrees")
    trials = read_jsonl(root_path / "trials.jsonl")
    observation_hash = completion.get("observation", {}).get("observation_sha256")
    require(valid_hash(observation_hash), "Missing fixed-observation hash")
    paired_trials: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in trials:
        key = tuple(row.get(field) for field in ("block", "num_steps", "phase", "call_index"))
        mode = row.get("instrumentation")
        require(key in expected and mode in ("off", "on") and (key, mode) not in paired_trials, "Unexpected/duplicate instrumentation trial")
        pair = keyed[key]
        require(row.get("pair_id") == pair["pair_id"], "Trial/pair identity mismatch")
        require(row.get("observation_sha256") == observation_hash and valid_hash(row.get("noise_sha256")), "Missing or inconsistent paired observation/noise hash")
        require(row.get("action_sha256") == pair[f"{mode}_action_sha256"], "Trial/pair action hash mismatch")
        require(all(row.get(f"{clock}_elapsed_ms") == pair[f"{mode}_{clock}_elapsed_ms"] for clock in ("host", "cuda")), "Trial/pair timing mismatch")
        noise_key = f"robopad-fixed-observation-v1:{config.get('seed')}:{key[0]}:{key[2]}:{key[3]}"
        expected_seed = int.from_bytes(hashlib.sha256(noise_key.encode()).digest()[:8], "big") % (2**63 - 1)
        require(type(config.get("seed")) is int and row.get("noise_seed") == expected_seed, "Trial noise seed differs from declared key")
        require(row.get("action_shape") == [1, 50, 7] and row.get("action_dtype") == "torch.float32", "Unexpected complete checkpoint action shape/dtype")
        require(type(row.get("action_index")) is int and row["action_index"] == len(paired_trials), "Action artifact indices are missing, duplicated, or out of journal order")
        hooks = row.get("instrumentation_counts")
        stages = row.get("stage_cuda_ms")
        if mode == "on":
            expected_hooks = {"chunk_entries": 1, "denoise_nfe": key[1], "prefill_forwards": 1, "action_expert_forwards": key[1]}
            require(isinstance(hooks, dict) and all(type(hooks.get(field)) is int and hooks[field] == value for field, value in expected_hooks.items()) and type(hooks.get("vision_encoder_calls")) is int and hooks["vision_encoder_calls"] >= 1, "Measured inference work counts disagree")
            require(isinstance(stages, dict) and set(stages) == {"embed_prefix", "vision_encoder", "prefill", "action_expert"} and all(positive_number(value, True) for value in stages.values()), "Invalid measured stage timings")
        else:
            require(hooks is None and stages is None, "Off-mode unexpectedly reports active model hooks")
        paired_trials[(key, mode)] = row
    require(set(paired_trials) == {(key, mode) for key in expected for mode in ("off", "on")}, "Missing on/off instrumentation trial")
    require(all(paired_trials[(key, "off")]["noise_sha256"] == paired_trials[(key, "on")]["noise_sha256"] for key in expected), "Instrumentation pair noise differs")
    for block in range(blocks):
        for phase, count in (("warmup", warmup), ("measurement", calls)):
            for index in range(count):
                require(len({paired_trials[((block, solver, phase, index), "off")]["noise_sha256"] for solver in solvers}) == 1, "Solver settings received different noise despite shared-noise contract")
    artifact = completion.get("actions_artifact", {})
    require(artifact.get("path") == "actions.pt" and artifact.get("count") == len(trials) and artifact.get("index_field") == "action_index" and valid_hash(artifact.get("sha256")), "Missing complete prediction tensor artifact metadata")
    require((root_path / "actions.pt").is_file() and file_sha(root_path / "actions.pt") == artifact["sha256"], "Prediction tensor artifact missing or digest differs")
    return [row for row in pairs if row["phase"] == "measurement"]
