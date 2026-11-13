from __future__ import annotations

import copy

import pytest

from reva.analysis import summarize_refinement_results


def fixture():
    return {
        "per_task": [
            {"task_group": "spatial", "task_id": 0, "metrics": {"successes": [True, False, True]}}
        ],
        "per_group": {"spatial": {"n_episodes": 3, "pc_success": 200 / 3}},
        "overall": {"n_episodes": 3, "pc_success": 200 / 3, "eval_s": 3.0},
        "robopad_ledger": {
            "select_action_calls": 6,
            "neural_chunk_calls": 3,
            "neural_chunk_seconds": [0.1, 0.2, 0.3],
        },
    }


def test_equal_calls_do_not_determine_host_interval_sum():
    first = summarize_refinement_results(fixture())
    second_data = fixture()
    second_data["robopad_ledger"]["neural_chunk_seconds"] = [0.4, 0.8, 1.2]
    second = summarize_refinement_results(second_data)
    assert first["neural_chunks"] == second["neural_chunks"]
    assert first["legacy_inference_host_seconds"] == pytest.approx(0.6)
    assert second["legacy_inference_host_seconds"] == pytest.approx(2.4)


def test_all_episodes_counted():
    result = summarize_refinement_results(fixture())
    assert (result["successes"], result["episodes"]) == (2, 3)
    assert result["control_to_neural"] == 2.0
    assert result["pairing_evidence"] == "unverifiable"


def test_completed_results_and_consistent_outcomes_are_required():
    faults = [
        lambda data: data.pop("overall"),
        lambda data: data["overall"].update(n_episodes=2),
        lambda data: data["overall"].update(pc_success=100.0),
        lambda data: data["per_group"]["spatial"].update(n_episodes=2),
        lambda data: data["per_group"]["spatial"].update(pc_success=100.0),
        lambda data: data["per_task"][0]["metrics"].update(successes=["false", False, True]),
        lambda data: data["per_task"].append(copy.deepcopy(data["per_task"][0])),
        lambda data: data["robopad_ledger"]["neural_chunk_seconds"].pop(),
        lambda data: data["robopad_ledger"]["neural_chunk_seconds"].append(float("nan")),
        lambda data: data["robopad_ledger"].update(neural_chunk_calls=0),
    ]
    for fault in faults:
        data = fixture()
        fault(data)
        with pytest.raises(ValueError):
            summarize_refinement_results(data)
