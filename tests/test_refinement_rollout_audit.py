import json

import pytest

from reva.analysis.refinement_query_recovery import canonical_sha
from reva.analysis.refinement_rollout_audit import check_initial_state, episode_key, reconcile_rollout_journal, reconcile_rollout_manifest


def _fixture(tmp_path):
    identity = {"suite": "suite", "task_id": 1, "initial_state_id": 2, "policy_seed": 3}
    schedule = [{"episode_identity": identity, "h": 1, "denoising_steps": 5, "planned_run_id": "run", "block_id": "block"}]
    runtime = {"selected_schedule": schedule, "selected_schedule_sha256": canonical_sha(schedule)}
    (tmp_path / "runtime_manifest.json").write_text(json.dumps(runtime), encoding="utf-8")
    row = {**schedule[0], "success": True, "runtime_manifest_sha256": canonical_sha(runtime)}
    completion = {"runtime_manifest_sha256": canonical_sha(runtime), "schedule_sha256": canonical_sha(schedule), "completed_attempts": 1, "expected_attempts": 1, "completed_blocks": 1, "episodes": [row], "aggregate_successes": 1}
    return runtime, row, completion


def test_manifest_reconciliation_binds_rows_to_declared_population(tmp_path):
    runtime, row, completion = _fixture(tmp_path)
    assert reconcile_rollout_manifest(tmp_path, completion, [row]) == runtime
    assert episode_key(row) == ("suite", 1, 2, 3)


def test_manifest_reconciliation_rejects_missing_planned_cell(tmp_path):
    _runtime, _row, completion = _fixture(tmp_path)
    with pytest.raises(ValueError, match="Missing declared"):
        reconcile_rollout_manifest(tmp_path, completion, [])


def test_manifest_reconciliation_rejects_row_manifest_tampering(tmp_path):
    _runtime, row, completion = _fixture(tmp_path)
    row["runtime_manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="manifest hash"):
        reconcile_rollout_manifest(tmp_path, completion, [row])


def test_journal_reconciliation_binds_generation_noise_and_terminal_record(tmp_path):
    import hashlib

    identity = {"suite": "suite", "task_id": 1, "initial_state_id": 2, "policy_seed": 3}
    state = {"dtype": "float64", "shape": [7], "values": [0.0] * 7}
    state["sha256"] = hashlib.sha256(b'["<f8",[7]]' + bytes(56)).hexdigest()
    action = {"dtype": "float64", "shape": [7], "values": [0.0] * 7}
    action["sha256"] = hashlib.sha256(b'["<f8",[7]]' + bytes(56)).hexdigest()
    row = {"run_id": "run", "episode_identity": identity, "initial_state": state, "initial_observation_sha256": "1" * 64, "h": 2, "steps": 2, "success": True, "termination_reason": "success", "independent_driver": {"terminal_record": {"reward": 1.0, "terminated": True, "truncated": False, "is_success": True}}}
    events = []
    for tick in range(2):
        seed = int.from_bytes(bytes.fromhex(canonical_sha(["policy_noise", identity, tick]))[:4], "little")
        events.append({"kind": "episode_start", "run_id": "run", "episode_identity": identity, "initial_state": state, "initial_observation_sha256": "1" * 64} if tick == 0 else {"kind": "step", "run_id": "run", "tick": tick, "new_generation": False, "generation_origin_tick": 0, "action_age_ticks": 1, "noise_seed": None, "producer_action": action, "environment_action_sha256": action["sha256"], "driver_terminated": True, "driver_truncated": False, "driver_is_success": True, "vector_terminated": True, "vector_truncated": False, "vector_is_success": True, "reward": 1.0})
        if tick == 0:
            events.append({"kind": "step", "run_id": "run", "tick": 0, "new_generation": True, "generation_origin_tick": 0, "action_age_ticks": 0, "noise_seed": seed, "producer_action": action, "environment_action_sha256": action["sha256"], "driver_terminated": False, "driver_truncated": False, "driver_is_success": False, "vector_terminated": False, "vector_truncated": False, "vector_is_success": False, "reward": 0.0})
    row["action_stream_sha256"] = canonical_sha([action["sha256"], action["sha256"]])
    events.append({"kind": "episode_completed", "run_id": "run", "success": True, "steps": 2, "action_stream_sha256": row["action_stream_sha256"]})
    (tmp_path / "steps.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    reconcile_rollout_journal(tmp_path, [row])
    check_initial_state(state)
