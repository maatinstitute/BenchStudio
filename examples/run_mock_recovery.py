#!/usr/bin/env python3
"""Demonstrate resumable frozen-plan execution with explicit accounting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reva.campaigns import CampaignExecutor, CampaignPlanner
from reva.mock import MockPolicy, MockSimulator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("runs/mock-recovery"))
    args = parser.parse_args()
    plan = CampaignPlanner(
        run_id="mock-recovery-checkpoint",
        scenario_id="recovery-task",
        conditions=[{"id": "baseline", "action_prefix": 1, "max_episode_steps": 4}],
        seeds=[1, 2, 3, 4],
    ).freeze()
    first = CampaignExecutor(
        plan,
        args.output,
        lambda _: MockPolicy(),
        lambda _: MockSimulator(),
    ).run(attempt_ids=[attempt.key.attempt_id for attempt in plan.attempts[:2]])
    resumed_executor = CampaignExecutor(
        plan,
        args.output,
        lambda _: MockPolicy(),
        lambda _: MockSimulator(),
    )
    resumed = resumed_executor.run()
    audit = resumed_executor.audit()
    report = {
        "schema": "reva.recovery_checkpoint.v1",
        "plan_digest_sha256": plan.plan_digest_sha256,
        "first_batch": {
            "committed": len(first.committed_attempt_ids),
            "missing": len(first.missing_attempt_ids),
        },
        "resumed_batch": {
            "committed": len(resumed.committed_attempt_ids),
            "skipped_existing": len(resumed.skipped_attempt_ids),
            "missing": len(resumed.missing_attempt_ids),
        },
        "audit": {
            "attempts_complete": audit.attempts_complete,
            "evidence_verified": audit.evidence_verified,
            "claim_status": audit.claim.status,
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "recovery-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if audit.attempts_complete and audit.evidence_verified else 2


if __name__ == "__main__":
    raise SystemExit(main())
