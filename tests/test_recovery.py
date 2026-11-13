import json

from ival.analysis import (
    load_recovery_records,
    summarize_recovery_outcomes,
    write_recovery_report,
)


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


def test_recovery_report_round_trips_records_and_summary(tmp_path):
    records = [
        {"pair_id": "p1", "branch": "nominal", "success": False},
        {
            "pair_id": "p1",
            "branch": "intervention",
            "success": True,
            "recovery_time_ms": 12,
        },
    ]
    records_path = tmp_path / "recovery.json"
    records_path.write_text(json.dumps({"records": records}), encoding="utf-8")
    report = summarize_recovery_outcomes(load_recovery_records(records_path))
    output = tmp_path / "recovery-report.json"
    write_recovery_report(report, output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "ival_recovery_report_v1"
    assert payload["matched_pairs"] == 1
