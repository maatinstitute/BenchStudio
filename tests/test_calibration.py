from __future__ import annotations

import pytest

from reva.calibration import CalibrationRecord, compare_calibrations


def _record(**overrides):
    value = {
        "revision": "cal-v1",
        "camera": "sha256:" + "1" * 64,
        "action_transform": "sha256:" + "2" * 64,
        "controller": "sha256:" + "3" * 64,
        "physical_parameters": "sha256:" + "4" * 64,
        "clock": "sha256:" + "5" * 64,
    }
    value.update(overrides)
    return CalibrationRecord.from_mapping(value)


def test_calibration_record_is_canonical_and_digestable():
    record = _record()
    assert record.to_dict()["revision"] == "cal-v1"
    assert record.digest_sha256().startswith("sha256:")


def test_calibration_comparison_identifies_transfer_mismatch():
    comparison = compare_calibrations(_record(), _record(camera="sha256:" + "9" * 64))
    assert comparison.compatible is False
    assert "camera calibration differs" in comparison.issues


def test_calibration_validation_rejects_malformed_digest():
    with pytest.raises(ValueError, match="camera"):
        _record(camera="not-a-digest")
