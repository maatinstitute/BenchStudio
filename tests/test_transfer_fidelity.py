from benchstudio.analysis import summarize_transfer_fidelity


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
