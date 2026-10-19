#!/usr/bin/env python3
"""Run matched mock campaigns through the transfer-fidelity report path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchstudio.campaigns import CampaignExecutor, CampaignPlanner
from benchstudio.compare import build_campaign_comparison_report
from benchstudio.mock import MockPolicy, MockSimulator


class BoundaryFixtureSimulator(MockSimulator):
    """A protocol fixture with a deliberately different success boundary."""

    simulator_id = "mock_physical_boundary_fixture"

    def step(self, action: int):
        self._step += 1
        self._success = self._step >= 5
        return self.observe()


def _plan():
    return CampaignPlanner(
        run_id="mock-transfer-checkpoint",
        scenario_id="fixture-task",
        conditions=[{"id": "baseline", "action_prefix": 1, "max_episode_steps": 4}],
        seeds=[1, 2, 3, 4],
        protocol={
            "P": {"task": {"task_id": "fixture-task", "revision": "mock-v1"}},
            "transfer_authority": "external",
        },
    ).freeze()


def _run(plan, output: Path, simulator_factory):
    executor = CampaignExecutor(
        plan,
        output,
        lambda _: MockPolicy(),
        simulator_factory,
    )
    return executor.run()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("runs/mock-transfer"))
    args = parser.parse_args()
    simulation = args.output / "simulation"
    physical_boundary = args.output / "physical-boundary-fixture"
    plan = _plan()
    simulation_result = _run(plan, simulation, lambda _: MockSimulator())
    physical_result = _run(plan, physical_boundary, lambda _: BoundaryFixtureSimulator())
    report = build_campaign_comparison_report(
        scenario_id="fixture-task",
        backend_campaigns={"simulation": simulation, "physical": physical_boundary},
        transfer_backends=("simulation", "physical"),
        transfer_system_id="mock-policy",
    )
    report["execution_and_scoring"] = "external"
    report["fixture_results"] = {
        "simulation": simulation_result.committed_attempt_ids,
        "physical_boundary": physical_result.committed_attempt_ids,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "transfer-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
