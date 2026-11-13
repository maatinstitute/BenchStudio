from __future__ import annotations

from dataclasses import dataclass

from ..conformance.replay_timing import ScheduledAction, apply_zero_order_hold


@dataclass(frozen=True)
class ReplayConformanceCase:
    case_id: str
    expected_actions: tuple[str | None, ...]
    resolved_actions: tuple[str | None, ...]

    @property
    def passed(self) -> bool:
        return self.expected_actions == self.resolved_actions


def zero_order_hold_case() -> ReplayConformanceCase:
    actions = [
        ScheduledAction("c0", 0, 0, "zero"),
        ScheduledAction("c1", 10, 20, "one"),
    ]
    resolved = apply_zero_order_hold(actions, [0, 10, 20, 30])
    return ReplayConformanceCase(
        "zero_order_hold",
        ("zero", "zero", "one", "one"),
        tuple(item.action if item else None for item in resolved),
    )


def run_replay_conformance() -> dict[str, object]:
    case = zero_order_hold_case()
    return {
        "profile": "worldepisode-replay-adapter-conformance-0.1",
        "source_basis": "leWorldDataset/tools/replay_adapter_conformance.py",
        "physics_coverage": "none",
        "cases": [{"case_id": case.case_id, "passed": case.passed}],
        "passed": case.passed,
    }
