from __future__ import annotations

import json
import math
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
