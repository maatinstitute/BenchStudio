import json

from ival.analysis import (
    load_transfer_records,
    summarize_transfer_fidelity,
    write_transfer_fidelity_report,
)


def test_transfer_fidelity_preserves_missingness_and_estimates_paired_gap():
    report = summarize_transfer_fidelity(
        [
            {
                "system_id": "a",
                "pair_id": "p1",
                "simulation_success": True,
                "physical_success": False,
                "simulation_failure_category": "none",
                "physical_failure_category": "grasp",
                "observation_age_ms": 10,
            },
            {
                "system_id": "a",
                "pair_id": "p2",
                "simulation_success": False,
                "physical_success": False,
                "simulation_failure_category": "contact",
                "physical_failure_category": "contact",
                "observation_age_ms": 20,
            },
            {
                "system_id": "a",
                "pair_id": "p3",
                "simulation_success": True,
                "physical_success": None,
            },
        ]
    )
    assert report.matched_pairs == 3
    assert report.complete_pairs == 2
    assert report.success_gap_physical_minus_simulation == -0.5
    assert report.success_gap_standard_error == 0.5
    assert report.success_gap_confidence_interval is not None
    assert (
        report.success_gap_confidence_interval[0] < -0.5 < report.success_gap_confidence_interval[1]
    )
    assert report.failure_category_agreement_rate == 0.5
    payload = report.to_dict()
    assert payload["schema"] == "ival_transfer_fidelity_report_v1"
    assert payload["success_gap_confidence_interval"] == list(
        report.success_gap_confidence_interval
    )
    assert report.mean_observation_age_ms == 15
    assert "some matched outcomes are missing" in report.issues


def test_transfer_fidelity_only_reports_ranking_with_sufficient_pairs():
    rows = []
    for system_id, sim, physical in (("a", True, True), ("b", False, False)):
        for index in range(2):
            rows.append(
                {
                    "system_id": system_id,
                    "pair_id": f"p{index}",
                    "simulation_success": sim,
                    "physical_success": physical,
                }
            )
    report = summarize_transfer_fidelity(rows)
    assert report.ranking_concordance == 1.0


def test_transfer_fidelity_artifact_round_trip(tmp_path):
    records = [
        {
            "system_id": "a",
            "pair_id": "p1",
            "simulation_success": True,
            "physical_success": True,
        }
    ]
    records_path = tmp_path / "records.json"
    records_path.write_text(json.dumps({"records": records}), encoding="utf-8")
    report = summarize_transfer_fidelity(load_transfer_records(records_path))
    output = tmp_path / "transfer.json"
    write_transfer_fidelity_report(report, output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "ival_transfer_fidelity_report_v1"
    assert payload["complete_pairs"] == 1


def test_transfer_fidelity_rejects_invalid_outcomes_and_ages():
    report = summarize_transfer_fidelity(
        [
            {
                "system_id": "a",
                "pair_id": "p1",
                "simulation_success": "yes",
                "physical_success": True,
                "observation_age_ms": -1,
            },
            {
                "system_id": "a",
                "pair_id": "p2",
                "simulation_success": True,
                "physical_success": False,
                "observation_age_ms": float("nan"),
            },
        ]
    )
    assert report.complete_pairs == 1
    assert any("must be boolean" in issue for issue in report.issues)
    assert any("observation_age_ms must be finite" in issue for issue in report.issues)


def test_transfer_gap_rejects_non_boolean_outcomes():
    from ival.analysis import estimate_transfer_gap

    gap = estimate_transfer_gap([True, "yes"], [False, True])
    assert gap.valid is False
    assert "invalid boolean outcome at index 1" in gap.issues
