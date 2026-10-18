from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ALPABRIDGE_DRIVER_TELEMETRY_SCHEMA = "alpabridge_driver_telemetry_v3"


@dataclass(frozen=True)
class AlpaBridgeTelemetryAudit:
    record_count: int
    drive_count: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_max_ms: float | None
    latency_target_missed: int
    model_load_failures: int
    route_sources: tuple[str, ...]
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


class AlpaBridgeTelemetryWriter:
    """Source-compatible v3 telemetry writer without the AlpaSim runtime.

    The owning driver can use this for deterministic evidence production;
    BenchStudio remains responsible for offline validation through
    :func:`audit_alpabridge_telemetry`.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path).expanduser() if path else None
        self._rows: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(self, row: dict[str, Any]) -> None:
        payload = {
            "schema": ALPABRIDGE_DRIVER_TELEMETRY_SCHEMA,
            "created_ns": time.time_ns(),
            **row,
        }
        with self._lock:
            self._rows.append(payload)
            if self._path is None:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def summary(self) -> dict[str, Any]:
        with self._lock:
            rows = list(self._rows)
        drive_rows = [row for row in rows if row.get("event") == "drive"]
        latencies = [
            float(row["latency_ms"])
            for row in drive_rows
            if isinstance(row.get("latency_ms"), (int, float))
            and math.isfinite(float(row["latency_ms"]))
        ]
        missed = [row for row in drive_rows if row.get("latency_target_met") is False]
        route_sources = sorted(
            {
                str(row.get("route_source"))
                for row in drive_rows
                if row.get("route_source") not in (None, "")
            }
        )
        return {
            "schema": "alpabridge_driver_telemetry_summary_v1",
            "event_count": len(rows),
            "drive_count": len(drive_rows),
            "latency_ms": {
                "p50": _percentile(latencies, 0.50),
                "p95": _percentile(latencies, 0.95),
                "max": max(latencies) if latencies else None,
            },
            "latency_target_missed": len(missed),
            "route_sources": route_sources,
            "telemetry_path": str(self._path) if self._path is not None else None,
        }


def load_alpabridge_telemetry(path: Path) -> AlpaBridgeTelemetryAudit:
    """Load AlpaBridge v3 JSONL telemetry without importing its runtime."""
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            issues.append(f"line {line_number}: invalid JSON")
            continue
        if not isinstance(record, dict):
            issues.append(f"line {line_number}: telemetry row must be an object")
            continue
        records.append(record)
    return audit_alpabridge_telemetry(records, issues=issues)


def audit_alpabridge_telemetry(
    records: Iterable[dict[str, Any]], *, issues: Iterable[str] = ()
) -> AlpaBridgeTelemetryAudit:
    rows = list(records)
    diagnostics = list(issues)
    drive_rows: list[dict[str, Any]] = []
    route_sources: set[str] = set()
    latencies: list[float] = []
    missed = 0
    model_load_failures = 0
    for index, row in enumerate(rows):
        if row.get("schema") != ALPABRIDGE_DRIVER_TELEMETRY_SCHEMA:
            diagnostics.append(f"record {index}: unexpected telemetry schema")
        event = row.get("event")
        if event == "model_load_failed":
            model_load_failures += 1
        if event != "drive":
            continue
        drive_rows.append(row)
        latency = row.get("latency_ms")
        if (
            not isinstance(latency, (int, float))
            or not math.isfinite(float(latency))
            or latency < 0
        ):
            diagnostics.append(f"record {index}: invalid drive latency_ms")
        else:
            latencies.append(float(latency))
        if not isinstance(row.get("latency_target_met"), bool):
            diagnostics.append(f"record {index}: latency_target_met must be boolean")
        elif row["latency_target_met"] is False:
            missed += 1
        route_source = row.get("route_source")
        if not isinstance(route_source, str) or not route_source:
            diagnostics.append(f"record {index}: route_source is required")
        else:
            route_sources.add(route_source)
    return AlpaBridgeTelemetryAudit(
        len(rows),
        len(drive_rows),
        _percentile(latencies, 0.50),
        _percentile(latencies, 0.95),
        max(latencies) if latencies else None,
        missed,
        model_load_failures,
        tuple(sorted(route_sources)),
        tuple(diagnostics),
    )


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
