from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paired import summarize_paired_outcomes


@dataclass(frozen=True)
class TransferGap:
    simulation_success_rate: float
    physical_success_rate: float
    physical_minus_simulation: float
    matched_pairs: int
    valid: bool
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "simulation_success_rate": self.simulation_success_rate,
            "physical_success_rate": self.physical_success_rate,
            "physical_minus_simulation": self.physical_minus_simulation,
            "matched_pairs": self.matched_pairs,
            "valid": self.valid,
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class TransferFidelityReport:
    matched_pairs: int
    complete_pairs: int
    simulation_success_rate: float | None
    physical_success_rate: float | None
    success_gap_physical_minus_simulation: float | None
    success_gap_standard_error: float | None
    success_gap_confidence_interval: tuple[float, float] | None
    success_agreement_rate: float | None
    failure_category_agreement_rate: float | None
    system_success_rates: dict[str, dict[str, float | int]]
    ranking_concordance: float | None
    mean_observation_age_ms: float | None
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "ival_transfer_fidelity_report_v1",
            "matched_pairs": self.matched_pairs,
            "complete_pairs": self.complete_pairs,
            "simulation_success_rate": self.simulation_success_rate,
            "physical_success_rate": self.physical_success_rate,
            "success_gap_physical_minus_simulation": self.success_gap_physical_minus_simulation,
            "success_gap_standard_error": self.success_gap_standard_error,
            "success_gap_confidence_interval": (
                list(self.success_gap_confidence_interval)
                if self.success_gap_confidence_interval is not None
                else None
            ),
            "success_agreement_rate": self.success_agreement_rate,
            "failure_category_agreement_rate": self.failure_category_agreement_rate,
            "system_success_rates": self.system_success_rates,
            "ranking_concordance": self.ranking_concordance,
            "mean_observation_age_ms": self.mean_observation_age_ms,
            "issues": list(self.issues),
        }


def load_transfer_records(path: Path) -> list[dict[str, Any]]:
    """Load transfer records from a JSON array, object, or JSONL file."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        values = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        values = json.loads(text)
        if isinstance(values, dict):
            values = values.get("records")
    if not isinstance(values, list) or not all(isinstance(value, dict) for value in values):
        raise ValueError("transfer records must be a JSON array or {records: [...]} mapping")
    return values


def write_transfer_fidelity_report(report: TransferFidelityReport, path: Path) -> None:
    """Write deterministic transfer-fidelity evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summarize_transfer_fidelity(records: list[dict[str, Any]]) -> TransferFidelityReport:
    """Summarize matched sim/physical records without imputing missing outcomes.

    Each record represents one system and matched condition. Required keys are
    ``pair_id``, ``simulation_success``, ``physical_success`` and ``system_id``.
    Missing booleans are excluded from paired estimates and reported as an issue.
    """
    issues: list[str] = []
    seen: set[tuple[str, str]] = set()
    pairs: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        pair_id = record.get("pair_id")
        system_id = record.get("system_id")
        if not isinstance(pair_id, str) or not pair_id:
            issues.append(f"record {index}: missing pair_id")
            continue
        if not isinstance(system_id, str) or not system_id:
            issues.append(f"record {index}: missing system_id")
            continue
        identity = (system_id, pair_id)
        if identity in seen:
            issues.append(f"duplicate system/pair record: {system_id}/{pair_id}")
            continue
        seen.add(identity)
        pairs.append(record)
    complete: list[dict[str, Any]] = []
    for index, record in enumerate(pairs):
        simulation = record.get("simulation_success")
        physical = record.get("physical_success")
        if not isinstance(simulation, bool) or not isinstance(physical, bool):
            issues.append(
                f"record {index}: simulation_success and physical_success must be boolean"
            )
            continue
        complete.append(record)
    if len(complete) < len(pairs):
        issues.append("some matched outcomes are missing")
    if not complete:
        return TransferFidelityReport(
            len(pairs),
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            {},
            None,
            None,
            tuple(issues + ["no complete matched pairs"]),
        )
    differences = [
        int(row["physical_success"]) - int(row["simulation_success"]) for row in complete
    ]
    paired = summarize_paired_outcomes(
        [row["simulation_success"] for row in complete],
        [row["physical_success"] for row in complete],
    )
    gap = sum(differences) / len(differences)
    standard_error = None
    if len(differences) > 1:
        mean = gap
        variance = sum((value - mean) ** 2 for value in differences) / (len(differences) - 1)
        standard_error = math.sqrt(variance / len(differences))
    agreements = sum(
        row["simulation_success"] == row["physical_success"] for row in complete
    ) / len(complete)
    category_rows = [
        row
        for row in complete
        if isinstance(row.get("simulation_failure_category"), str)
        and isinstance(row.get("physical_failure_category"), str)
    ]
    category_agreement = (
        sum(
            row["simulation_failure_category"] == row["physical_failure_category"]
            for row in category_rows
        )
        / len(category_rows)
        if category_rows
        else None
    )
    system_rates = _system_rates(complete)
    concordance = _ranking_concordance(system_rates)
    ages: list[float] = []
    for index, row in enumerate(complete):
        age = row.get("observation_age_ms")
        if age is None:
            continue
        if (
            isinstance(age, bool)
            or not isinstance(age, (int, float))
            or not math.isfinite(float(age))
            or age < 0
        ):
            issues.append(
                f"complete record {index}: observation_age_ms must be finite and non-negative"
            )
            continue
        ages.append(float(age))
    return TransferFidelityReport(
        len(pairs),
        len(complete),
        sum(row["simulation_success"] for row in complete) / len(complete),
        sum(row["physical_success"] for row in complete) / len(complete),
        gap,
        standard_error,
        paired.success_gap_confidence_interval,
        agreements,
        category_agreement,
        system_rates,
        concordance,
        sum(ages) / len(ages) if ages else None,
        tuple(issues),
    )


def estimate_transfer_gap(
    simulation_successes: list[bool | None], physical_successes: list[bool | None]
) -> TransferGap:
    if len(simulation_successes) != len(physical_successes):
        return TransferGap(0.0, 0.0, 0.0, 0, False, ("paired inputs must have equal length",))
    invalid = [
        index
        for index, (simulation, physical) in enumerate(
            zip(simulation_successes, physical_successes)
        )
        if (simulation is not None and not isinstance(simulation, bool))
        or (physical is not None and not isinstance(physical, bool))
    ]
    pairs = [
        (simulation, physical)
        for simulation, physical in zip(simulation_successes, physical_successes)
        if isinstance(simulation, bool) and isinstance(physical, bool)
    ]
    if not pairs:
        issues = (["invalid boolean outcome at index " + str(index) for index in invalid]) + [
            "no complete matched pairs"
        ]
        return TransferGap(0.0, 0.0, 0.0, 0, False, tuple(issues))
    simulation_rate = sum(simulation for simulation, _ in pairs) / len(pairs)
    physical_rate = sum(physical for _, physical in pairs) / len(pairs)
    issues = ["some outcomes are missing"] if len(pairs) != len(simulation_successes) else []
    issues.extend("invalid boolean outcome at index " + str(index) for index in invalid)
    return TransferGap(
        simulation_rate,
        physical_rate,
        physical_rate - simulation_rate,
        len(pairs),
        not issues,
        tuple(issues),
    )


def _system_rates(records: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record["system_id"]), []).append(record)
    return {
        system_id: {
            "matched_pairs": len(rows),
            "simulation_success_rate": sum(row["simulation_success"] for row in rows) / len(rows),
            "physical_success_rate": sum(row["physical_success"] for row in rows) / len(rows),
        }
        for system_id, rows in sorted(grouped.items())
    }


def _ranking_concordance(rates: dict[str, dict[str, float | int]]) -> float | None:
    if len(rates) < 2 or any(int(row["matched_pairs"]) < 2 for row in rates.values()):
        return None
    systems = sorted(rates)
    agreements = 0
    comparisons = 0
    for index, left in enumerate(systems):
        for right in systems[index + 1 :]:
            sim_delta = float(rates[left]["simulation_success_rate"]) - float(
                rates[right]["simulation_success_rate"]
            )
            physical_delta = float(rates[left]["physical_success_rate"]) - float(
                rates[right]["physical_success_rate"]
            )
            comparisons += 1
            agreements += int(
                sim_delta == 0 or physical_delta == 0 or sim_delta * physical_delta > 0
            )
    return agreements / comparisons if comparisons else None
