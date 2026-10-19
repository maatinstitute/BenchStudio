import json

import pytest

from benchstudio.analysis.refinement_query_recovery import canonical_sha
from benchstudio.analysis.refinement_rollout_audit import episode_key, reconcile_rollout_manifest


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
