import hashlib
import json

import pytest

from ival.analysis.refinement_microbenchmark import validate_microbenchmark


def test_microbenchmark_validator_reconciles_pairs_trials_and_artifact(tmp_path):
    action = "a" * 64
    observation = "b" * 64
    noise = "c" * 64
    config = {"blocks": 1, "num_steps": [5], "calls": 1, "warmup_calls": 0, "rtol": 1e-5, "atol": 1e-6, "seed": 1000}
    pair = {"pair_id": "b0:d5:measurement:0", "block": 0, "num_steps": 5, "phase": "measurement", "call_index": 0, "allclose": True, "exact_equal": True, "max_abs_diff": 0.0, "rtol": 1e-5, "atol": 1e-6, "off_action_sha256": action, "on_action_sha256": action, "off_host_elapsed_ms": 10.0, "on_host_elapsed_ms": 11.0, "off_cuda_elapsed_ms": 5.0, "on_cuda_elapsed_ms": 5.5}
    trials = []
    for mode, host, cuda in (("off", 10.0, 5.0), ("on", 11.0, 5.5)):
        key = "robopad-fixed-observation-v1:1000:0:measurement:0"
        trials.append({"pair_id": pair["pair_id"], "block": 0, "num_steps": 5, "phase": "measurement", "call_index": 0, "instrumentation": mode, "action_sha256": action, "noise_sha256": noise, "noise_seed": int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") % (2**63 - 1), "observation_sha256": observation, "action_shape": [1, 50, 7], "action_dtype": "torch.float32", "action_index": len(trials), "instrumentation_counts": {"chunk_entries": 1, "denoise_nfe": 5, "vision_encoder_calls": 1, "prefill_forwards": 1, "action_expert_forwards": 5} if mode == "on" else None, "stage_cuda_ms": {"embed_prefix": 1.0, "vision_encoder": 1.0, "prefill": 1.0, "action_expert": 1.0} if mode == "on" else None, "host_elapsed_ms": host, "cuda_elapsed_ms": cuda})
    (tmp_path / "pairs.jsonl").write_text(json.dumps(pair) + "\n", encoding="utf-8")
    (tmp_path / "trials.jsonl").write_text("\n".join(json.dumps(row) for row in trials) + "\n", encoding="utf-8")
    (tmp_path / "actions.pt").write_bytes(b"fixture")
    summary = {"status": "complete", "config": config, "planned_actual_chunk_generations": 2, "observation": {"observation_sha256": observation}, "counts": {"completed_actual_chunk_generations": 2, "issued_prediction_calls": 2, "completed_pairs": 1, "unpaired_calls": 0, "measured_calls": 2, "warmup_calls": 0, "pairs_allclose": 1, "pairs_exact_equal": 1}, "actions_artifact": {"path": "actions.pt", "sha256": hashlib.sha256(b"fixture").hexdigest(), "count": 2, "index_field": "action_index"}}
    assert len(validate_microbenchmark(tmp_path, summary)) == 1


def test_microbenchmark_validator_rejects_missing_pair(tmp_path):
    with pytest.raises(ValueError, match="Microbenchmark must be complete"):
        validate_microbenchmark(tmp_path, {"status": "partial"})
