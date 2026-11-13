from __future__ import annotations

import json
import subprocess
import sys

from benchstudio.campaigns import AttemptLedger, load_frozen_campaign_plan


def test_independent_process_shards_commit_one_complete_campaign(tmp_path):
    spec = tmp_path / "campaign.json"
    plan = tmp_path / "campaign-plan.json"
    output = tmp_path / "run"
    spec.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "process-cluster"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1, 2, 3, 4, 5, 6, 7, 8],
                    "paired": True,
                    "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
                },
            }
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "benchstudio.cli",
            "--campaign-spec",
            str(spec),
            "--plan-output",
            str(plan),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "benchstudio.cli",
                "--frozen-plan",
                str(plan),
                "--execute-mock",
                "--shard-index",
                str(index),
                "--shard-count",
                "2",
                "--worker-id",
                f"process-{index}",
                "--output",
                str(output),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(2)
    ]
    completed = [process.communicate(timeout=30) for process in processes]
    for process, (stdout, stderr) in zip(processes, completed, strict=True):
        assert process.returncode == 0, f"stdout:\n{stdout}\nstderr:\n{stderr}"
        assert "campaign_status=completed" in stdout
        assert "scope=shard" in stdout

    frozen = load_frozen_campaign_plan(plan)
    ledger = AttemptLedger(output / "attempt-results.jsonl", frozen)
    assert ledger.missing_attempt_ids == []
    assert len(ledger.records) == 8
    assert len({record["attempt_id"] for record in ledger.records}) == 8
    assert {record["status"] for record in ledger.records} == {"completed"}
