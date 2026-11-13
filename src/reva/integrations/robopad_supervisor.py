"""RoboPAD's bounded development-child supervisor contract.

This module owns only the process-boundary safeguards. Campaign scheduling,
manifest construction, and the child runtime remain external to REVA.
"""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable, Sequence

LOG_CAP = 500_000
RECEIPT_CAP = 50_000
TIMEOUT = 3330
KILL_AFTER = 5


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stop_group(process: subprocess.Popen[bytes], *, grace: float = KILL_AFTER) -> None:
    """Terminate an owned process group, escalating after the grace period."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class SupervisorInterrupted(Exception):
    """Raised when the supervisor receives an external termination signal."""


def _interrupted(signum: int, _frame: object) -> None:
    raise SupervisorInterrupted(f"external signal {signum}")


def supervise(
    command: Sequence[str],
    log_path: Path,
    *,
    timeout: float = TIMEOUT,
    log_cap: int = LOG_CAP,
    grace: float = KILL_AFTER,
) -> dict[str, object]:
    """Run one owned child with bounded merged output and no retries.

    The child is placed in a new process group so timeout, output overflow, and
    supervisor interruption clean up descendants as one unit. The log is
    exclusive and bounded; a second attempt cannot overwrite the evidence.
    """
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    selector = selectors.DefaultSelector()
    result: dict[str, object] = {
        "status": "starting",
        "log_bytes": 0,
        "timeout_seconds": timeout,
        "log_cap_bytes": log_cap,
        "retries": 0,
    }
    previous_handlers: dict[int, object] = {}
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[sig] = signal.signal(sig, _interrupted)
        with log_path.open("xb") as log:
            process = subprocess.Popen(
                list(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            result["child_pid"] = process.pid
            assert process.stdout is not None
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    result["status"] = "timeout"
                    stop_group(process, grace=grace)
                    break
                events = selector.select(min(0.1, remaining))
                for key, _ in events:
                    chunk = os.read(key.fileobj.fileno(), 32768)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    room = log_cap - int(result["log_bytes"])
                    retained = chunk[: max(0, room)]
                    if retained:
                        if log.write(retained) != len(retained):
                            raise OSError("short supervisor log write")
                        result["log_bytes"] = int(result["log_bytes"]) + len(retained)
                    if len(chunk) > room:
                        result["status"] = "log_limit_exceeded"
                        stop_group(process, grace=grace)
                        break
                if result["status"] != "starting":
                    break
            if result["status"] == "starting":
                remaining = timeout - (time.monotonic() - started)
                try:
                    code = process.wait(timeout=max(0, remaining))
                    result["status"] = "completed" if code == 0 else "child_failed"
                except subprocess.TimeoutExpired:
                    result["status"] = "timeout"
                    stop_group(process, grace=grace)
            try:
                result["returncode"] = process.wait(timeout=max(1, grace))
            except subprocess.TimeoutExpired:
                result["returncode"] = None
                result["status"] = "termination_unconfirmed"
            if result["status"] in ("completed", "child_failed"):
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    result["leader_status"] = result["status"]
                    result["status"] = "lingering_process_group"
                    stop_group(process, grace=grace)
            log.flush()
    except BaseException as exc:
        result.update(
            status="external_signal"
            if isinstance(exc, SupervisorInterrupted)
            else "supervisor_failure",
            error=repr(exc)[:2000],
        )
        for sig in previous_handlers:
            signal.signal(sig, signal.SIG_IGN)
        if process is not None:
            try:
                stop_group(process, grace=grace)
                result["returncode"] = process.wait(timeout=max(1, grace))
            except BaseException as error:
                result["termination_error"] = repr(error)[:1000]
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        selector.close()
        if process is not None and process.stdout is not None:
            process.stdout.close()
        result["elapsed_seconds"] = time.monotonic() - started
    return result


def write_receipt(path: Path, result: dict[str, object], *, receipt_cap: int = RECEIPT_CAP) -> None:
    """Atomically publish one bounded supervisor receipt."""
    blob = (json.dumps(result, indent=2, allow_nan=False) + "\n").encode()
    if len(blob) > receipt_cap:
        raise ValueError("supervisor receipt ceiling")
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("xb") as stream:
        if stream.write(blob) != len(blob):
            raise OSError("short receipt write")
    temporary.replace(path)


def select_timeout(config: dict[str, object], child_runs: Callable[[int, int], object]) -> int:
    """Select RoboPAD's fixed reviewed parent envelope without coercion."""
    task, demo = config["task"], config["demo"]
    if (
        type(task) is not int
        or type(demo) is not int
        or (task, demo) not in ((0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1))
    ):
        raise ValueError("unreviewed supervisor parent")
    if config["runs"] != child_runs(task, demo):
        raise ValueError("noncanonical run list")
    limits = config["limits"]
    if not isinstance(limits, dict):
        raise ValueError("not reviewed limits")
    if (task, demo) == (0, 0):
        if any(
            type(limits.get(key)) is not int or not 0 < limits[key] <= cap
            for key, cap in (("application_seconds", 3300), ("total_bytes", 4_000_000_000))
        ):
            raise ValueError("not reviewed first-child envelope")
        return 3330
    expected = dict(
        application_seconds=7200,
        total_bytes=4_500_000_000,
        cell_bytes=70_000_000,
        cache_bytes=20_000_000,
        accounting_bytes=1_000_000,
        max_actions=12400,
        max_suffix_queries=1240,
        max_cache_queries=6,
    )
    if set(limits) != set(expected) or any(
        type(limits[key]) is not int or limits[key] != value for key, value in expected.items()
    ):
        raise ValueError("not reviewed next-child limits")
    if (
        type(config.get("cell_runtime_reserve_seconds")) is not int
        or config["cell_runtime_reserve_seconds"] != 240
    ):
        raise ValueError("not reviewed next-child start reserve")
    return 7230
