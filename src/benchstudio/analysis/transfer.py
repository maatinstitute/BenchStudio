from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransferGap:
    simulation_success_rate: float
    physical_success_rate: float
    physical_minus_simulation: float
    matched_pairs: int
    valid: bool
    issues: tuple[str, ...]


def estimate_transfer_gap(
    simulation_successes: list[bool | None], physical_successes: list[bool | None]
) -> TransferGap:
    if len(simulation_successes) != len(physical_successes):
        return TransferGap(0.0, 0.0, 0.0, 0, False, ("paired inputs must have equal length",))
    pairs = [
        (simulation, physical)
        for simulation, physical in zip(simulation_successes, physical_successes)
        if simulation is not None and physical is not None
    ]
    if not pairs:
        return TransferGap(0.0, 0.0, 0.0, 0, False, ("no complete matched pairs",))
    simulation_rate = sum(simulation for simulation, _ in pairs) / len(pairs)
    physical_rate = sum(physical for _, physical in pairs) / len(pairs)
    return TransferGap(
        simulation_rate,
        physical_rate,
        physical_rate - simulation_rate,
        len(pairs),
        len(pairs) == len(simulation_successes),
        () if len(pairs) == len(simulation_successes) else ("some outcomes are missing",),
    )
