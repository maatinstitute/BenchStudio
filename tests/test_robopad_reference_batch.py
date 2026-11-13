from unittest.mock import patch

import pytest

from ival.campaigns.robopad_reference_batch import NAMES, dispatch, reserve, slots


def test_exact_remaining_slots_and_duplicate_claim(tmp_path):
    assert sum(len(slots(name)) for name in NAMES) == 32
    assert len(slots(NAMES[0])) == 2
    claims = tmp_path / "claims"
    reserved: list[str] = []
    reserve(claims, NAMES, "first", reserved)
    assert len(reserved) == 32
    before = {path.name: path.read_bytes() for path in claims.iterdir()}
    with pytest.raises(RuntimeError):
        reserve(claims, NAMES, "second", [])
    assert before == {path.name: path.read_bytes() for path in claims.iterdir()}


def test_partial_reservation_failure_remains_claimed(tmp_path):
    claims = tmp_path / "claims"
    reserved: list[str] = []
    with patch(
        "ival.campaigns.robopad_reference_batch.json.dump",
        side_effect=OSError("write failed"),
    ):
        with pytest.raises(OSError):
            reserve(claims, NAMES, "owner", reserved)
    assert reserved == [slots(NAMES[0])[0]]
    assert (claims / (reserved[0] + ".json")).exists()
    with pytest.raises(RuntimeError):
        reserve(claims, NAMES, "other", [])


def test_nonzero_stops_and_preserves_started_terminal_accounting(tmp_path):
    report = {"children": []}
    calls: list[str] = []
    snapshots: list[list[str]] = []

    def execute(name: str) -> int:
        calls.append(name)
        return 124

    def save() -> None:
        snapshots.append([row["status"] for row in report["children"]])

    with pytest.raises(RuntimeError):
        dispatch(tmp_path, report, save, 0, execute=execute, clock=lambda: 0)
    assert calls == [NAMES[0]]
    assert snapshots == [["started"], ["terminal"]]
    assert report["children"][0]["returncode"] == 124


def test_reserve_time_prevents_child_start(tmp_path):
    report = {"children": []}
    with pytest.raises(TimeoutError):
        dispatch(
            tmp_path,
            report,
            lambda: None,
            0,
            execute=lambda _: pytest.fail("started"),
            clock=lambda: 3266,
        )
    assert report["children"] == []
