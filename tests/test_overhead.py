import json

import pytest

from benchstudio.analysis import (
    TimingProvenance,
    audit_execution_overhead,
    load_execution_overhead,
    write_execution_overhead,
)


def test_execution_overhead_reports_added_latency_and_deadline_misses():
    report = audit_execution_overhead([10.0, 12.0], [11.0, 16.0], deadline_ms=15.0)
    assert report.valid is True
    assert report.matched_samples == 2
    assert report.added_mean_ms == pytest.approx(2.5)
    assert report.relative_overhead == pytest.approx(2.5 / 11.0)
    assert report.baseline_deadline_misses == 0
    assert report.instrumented_deadline_misses == 1


def test_execution_overhead_rejects_unmatched_or_invalid_samples():
    assert not audit_execution_overhead([1.0], [1.0, 2.0]).valid
    report = audit_execution_overhead([1.0, float("nan")], [1.0, 2.0])
    assert report.valid is False
    assert "baseline[1]" in report.issues[0]


def test_execution_overhead_preserves_clock_boundaries_and_uncertainty():
    report = audit_execution_overhead(
        [10.0],
        [11.0],
        timing_provenance=TimingProvenance(
            "host_monotonic", "inference_start", "inference_end", uncertainty_ms=0.2
        ),
    )
    assert report.valid is True
    assert report.provenance_complete is True
    assert report.to_dict()["timing_provenance"]["clock_domain"] == "host_monotonic"


def test_execution_overhead_round_trips_as_a_campaign_evidence_artifact(tmp_path):
    report = audit_execution_overhead(
        [10.0, 12.0],
        [11.0, 16.0],
        deadline_ms=15.0,
        timing_provenance=TimingProvenance(
            "host_monotonic", "inference_start", "inference_end", uncertainty_ms=0.1
        ),
    )
    path = tmp_path / "execution-overhead.json"
    write_execution_overhead(report, path)
    loaded = load_execution_overhead(path)
    assert loaded == report
    assert json.loads(path.read_text())["schema"] == "benchstudio_execution_overhead_v1"
