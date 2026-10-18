from benchstudio.analysis import summarize_recovery_outcomes


def test_recovery_summary_preserves_missing_branches_and_latency():
    report = summarize_recovery_outcomes(
        [
            {"pair_id": "p1", "branch": "nominal", "success": True},
            {
                "pair_id": "p1",
                "branch": "intervention",
                "success": True,
                "recovery_time_ms": 120,
            },
            {"pair_id": "p2", "branch": "nominal", "success": True},
        ]
    )
    assert report.scheduled_pairs == 2
    assert report.matched_pairs == 1
    assert report.missing_pairs == 1
    assert report.recovery_rate == 1.0
    assert report.recovery_confidence_interval is not None
    assert report.mean_recovery_time_ms == 120
    assert report.issues == ("some nominal/intervention branches are missing",)


def test_recovery_summary_does_not_treat_missing_outcome_as_failure():
    report = summarize_recovery_outcomes(
        [
            {"pair_id": "p1", "branch": "nominal", "success": True},
            {"pair_id": "p1", "branch": "intervention", "success": None},
        ]
    )
    assert report.matched_pairs == 0
    assert report.recovery_rate is None
    assert "some matched branches have missing outcomes" in report.issues
