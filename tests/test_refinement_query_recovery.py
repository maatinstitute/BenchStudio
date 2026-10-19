import pytest

from benchstudio.analysis.refinement_query_recovery import (
    QUERY_RECOVERY_PROTOCOL,
    audit_query_recovery,
    query_answer_check,
    recover_direct_query,
)


def test_direct_recovery_preserves_unknown_and_zero_success_semantics():
    queries = {query["id"]: query for query in QUERY_RECOVERY_PROTOCOL["queries"]}
    rows = [{"attempt_id": "a", "success": True, "rollout_wall_s": 2.0, "generations": 3, "denoise_nfe": 9}, {"attempt_id": "b", "success": False, "rollout_wall_s": 4.0, "generations": 2, "denoise_nfe": 6}]
    assert recover_direct_query(queries["success_attempts"], rows)["value"] == {"successes": 1, "attempts": 2}
    assert recover_direct_query(queries["wall_per_success_s"], [{"success": False, "rollout_wall_s": 4.0}])["status"] == "undefined"
    assert recover_direct_query(queries["rollout_wall_s"], [{"attempt_id": "a", "success": True}])["status"] == "unknown"


def test_query_answer_check_does_not_treat_unknown_as_wrong():
    assert query_answer_check({"status": "unknown", "value": None}, {"status": "recovered", "value": 1}) is None
    assert query_answer_check({"status": "recovered", "value": 1.0}, {"status": "recovered", "value": 1.0}) is True


def test_four_cell_audit_reuses_reconciled_reference_values():
    rows = []
    for h, d in ((1, 5), (1, 10), (5, 5), (5, 10)):
        for index, success in enumerate((True, False)):
            rows.append({"run_id": f"{h}-{d}-{index}", "h": h, "denoising_steps": d, "success": success, "steps": 5, "counts": {"generations": 5 if h == 1 else 1, "denoise_steps": d * (5 if h == 1 else 1)}, "timing": {"rollout_wall_s": 2.0 + index}, "independent_driver": {"success": success}})
    report = audit_query_recovery(rows, {"runtime": "fixed"})
    assert report["status"] == "complete"
    assert report["unique_queries"] == 24
    assert report["projection_checks"] == 72
    assert all(row["wrong_answers"] == 0 for row in report["summary"])


def test_query_recovery_rejects_unlocked_cells():
    with pytest.raises(ValueError, match="locked four cells"):
        audit_query_recovery([], {})
