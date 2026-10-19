#!/usr/bin/env python3
"""Run a frozen campaign with multiple lease-owning workers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchstudio.campaigns import CampaignExecutor, CampaignPlanner
from benchstudio.mock import MockPolicy, MockSimulator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("runs/mock-workers"))
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.workers < 2:
        parser.error("--workers must be at least 2")
    plan = CampaignPlanner(
        run_id="mock-workers-checkpoint",
        scenario_id="worker-task",
        conditions=[{"id": "baseline", "action_prefix": 1, "max_episode_steps": 4}],
        seeds=list(range(1, 9)),
    ).freeze()
    executor = CampaignExecutor(
        plan,
        args.output,
        lambda _: MockPolicy(),
        lambda _: MockSimulator(),
    )
    result = executor.run_parallel(args.workers)
    audit = executor.audit()
    report = {
        "schema": "benchstudio.worker_checkpoint.v1",
        "workers": args.workers,
        "planned": len(plan.attempts),
        "committed": len(result.committed_attempt_ids),
        "failed": len(result.failed_attempt_ids),
        "leased_out": len(result.leased_out_attempt_ids),
        "missing": len(result.missing_attempt_ids),
        "audit": {
            "attempts_complete": audit.attempts_complete,
            "evidence_verified": audit.evidence_verified,
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "worker-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if report["committed"] == report["planned"] and report["audit"]["attempts_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
