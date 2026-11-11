import json

import pytest

from benchstudio.integrations import (
    AlpaBridgeTelemetryWriter,
    load_alpabridge_telemetry,
    route_arc_length_m,
)


def _row(event: str, **fields):
    return {"schema": "alpabridge_driver_telemetry_v3", "event": event, **fields}


def test_alpabridge_telemetry_preserves_latency_misses_and_route_provenance(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(_row("model_loaded")),
                json.dumps(
                    _row(
                        "drive",
                        latency_ms=10.0,
                        latency_target_met=True,
                        route_source="alpasim_waypoints",
                    )
                ),
                json.dumps(
                    _row(
                        "drive",
                        latency_ms=30.0,
                        latency_target_met=False,
                        route_source="command_proxy",
                    )
                ),
                json.dumps(_row("model_load_failed")),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    audit = load_alpabridge_telemetry(path)
    assert audit.valid is True
    assert audit.drive_count == 2
    assert audit.latency_p95_ms == 29.0
    assert audit.latency_target_missed == 1
    assert audit.model_load_failures == 1
    assert audit.route_sources == ("alpasim_waypoints", "command_proxy")


def test_alpabridge_telemetry_rejects_malformed_drive_contract(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    path.write_text(
        json.dumps(
            _row("drive", latency_ms=float("nan"), latency_target_met="yes") | {"route_source": ""}
        )
        + "\n",
        encoding="utf-8",
    )
    audit = load_alpabridge_telemetry(path)
    assert audit.valid is False
    assert any("invalid drive latency_ms" in issue for issue in audit.issues)
    assert any("latency_target_met" in issue for issue in audit.issues)
    assert any("route_source" in issue for issue in audit.issues)


def test_alpabridge_telemetry_writer_matches_source_summary_contract(tmp_path):
    path = tmp_path / "written-telemetry.jsonl"
    writer = AlpaBridgeTelemetryWriter(path)
    writer.record({"event": "model_loaded"})
    writer.record(
        {
            "event": "drive",
            "latency_ms": 10.0,
            "latency_target_met": True,
            "route_source": "alpasim_waypoints",
        }
    )
    writer.record(
        {
            "event": "drive",
            "latency_ms": 30.0,
            "latency_target_met": False,
            "route_source": "command_proxy",
        }
    )
    summary = writer.summary()
    assert summary["schema"] == "alpabridge_driver_telemetry_summary_v1"
    assert summary["drive_count"] == 2
    assert summary["latency_target_missed"] == 1
    assert summary["latency_ms"]["p95"] == 29.0
    assert load_alpabridge_telemetry(path).valid


def test_route_arc_length_follows_the_ground_plane_path():
    assert route_arc_length_m(
        [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 3.0, "y": 0.0, "z": 0.0},
            {"x": 3.0, "y": 4.0, "z": 5.0},
        ]
    ) == pytest.approx(7.0)
    assert route_arc_length_m([]) == 0.0
