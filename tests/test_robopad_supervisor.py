import copy
import signal
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from ival.integrations.robopad_supervisor import (
    select_timeout,
    supervise,
)


def _runs(task: int, demo: int) -> list[tuple[int, int]]:
    count = 1 if (task, demo) == (0, 0) else 62
    return [(task, demo + index) for index in range(count)]


def _config(demo: int, task: int = 0) -> dict[str, object]:
    limits: dict[str, int] = dict(
        application_seconds=7200,
        total_bytes=4_500_000_000,
        cell_bytes=70_000_000,
        cache_bytes=20_000_000,
        accounting_bytes=1_000_000,
        max_actions=12400,
        max_suffix_queries=1240,
        max_cache_queries=6,
    )
    if (task, demo) == (0, 0):
        limits.update(application_seconds=3300, total_bytes=4_000_000_000)
    return {
        "task": task,
        "demo": demo,
        "runs": _runs(task, demo),
        "limits": limits,
        "cell_runtime_reserve_seconds": 240,
    }


def test_fixed_timeouts_and_rejected_changes():
    for demo, timeout in ((0, 3330), (1, 7230)):
        config = _config(demo)
        assert select_timeout(config, _runs) == timeout
        if demo:
            bad = copy.deepcopy(config)
            bad["runs"].reverse()
            with pytest.raises(ValueError, match="canonical"):
                select_timeout(bad, _runs)
    config = _config(1)
    for key in config["limits"]:
        bad = copy.deepcopy(config)
        bad["limits"][key] += 1
        with pytest.raises(ValueError, match="reviewed"):
            select_timeout(bad, _runs)
    for changes in (
        {"task": 3},
        {"task": True},
        {"demo": 2},
        {"demo": True},
        {"cell_runtime_reserve_seconds": 241},
    ):
        bad = copy.deepcopy(config)
        bad.update(changes)
        with pytest.raises(ValueError):
            select_timeout(bad, _runs)


def test_remaining_fixed_parents_use_same_bounded_envelope():
    for task, demo in ((1, 0), (1, 1), (2, 0), (2, 1)):
        config = _config(demo, task)
        assert len(config["runs"]) == 62
        assert select_timeout(config, _runs) == 7230
        bad = copy.deepcopy(config)
        bad["limits"]["application_seconds"] = 3300
        with pytest.raises(ValueError):
            select_timeout(bad, _runs)


def _run_child(script: str, root: Path, **kwargs: object) -> dict[str, object]:
    return supervise(
        [sys.executable, "-u", "-c", script], root / "log", grace=0.05, timeout=2, **kwargs
    )


def test_success_nonzero_and_exclusive_log(tmp_path):
    result = _run_child("print('small');raise SystemExit(3)", tmp_path)
    assert result["status"] == "child_failed"
    assert result["returncode"] == 3
    before = (tmp_path / "log").read_bytes()
    result = _run_child("print('overwrite')", tmp_path)
    assert result["status"] == "supervisor_failure"
    assert (tmp_path / "log").read_bytes() == before


def test_overflow_bounds_bytes_and_stops_child(tmp_path):
    result = _run_child(
        "import os,time;os.write(1,b'x'*10000);time.sleep(30)", tmp_path, log_cap=100
    )
    assert result["status"] == "log_limit_exceeded"
    assert (tmp_path / "log").stat().st_size == 100
    assert result["returncode"] is not None
    assert result["elapsed_seconds"] < 2


def test_external_signal_cleans_owned_child_and_restores_handler(tmp_path):
    before = signal.getsignal(signal.SIGTERM)
    result = _run_child(
        "import os,signal,time;os.kill(os.getppid(),signal.SIGTERM);time.sleep(30)", tmp_path
    )
    assert result["status"] == "external_signal"
    assert result["returncode"] is not None
    assert signal.getsignal(signal.SIGTERM) is before


def test_lingering_group_is_not_success(tmp_path):
    with (
        patch("ival.integrations.robopad_supervisor.os.killpg", return_value=None),
        patch("ival.integrations.robopad_supervisor.stop_group") as stop,
    ):
        result = _run_child("print('done')", tmp_path)
    assert result["status"] == "lingering_process_group"
    stop.assert_called_once()


def test_timeout_kills_term_ignoring_group(tmp_path):
    result = supervise(
        [
            sys.executable,
            "-u",
            "-c",
            "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(30)",
        ],
        tmp_path / "log",
        timeout=0.2,
        grace=0.05,
    )
    assert result["status"] == "timeout"
    assert result["returncode"] is not None
    assert result["elapsed_seconds"] < 2
