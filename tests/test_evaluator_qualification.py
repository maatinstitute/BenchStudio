import hashlib
import json

import tempfile
import unittest
from pathlib import Path

from benchstudio.analysis.evaluator_qualification import build_evaluator_report
from benchstudio.campaigns.frozen_plan import (
    AttemptKey,
    FrozenCampaignPlan,
    PlannedAttempt,
    _plan_digest,
)
from benchstudio.campaigns.qualification import verify_refinement_qualification

RUNTIME = dict.fromkeys(
    ("runner", "checkpoint", "simulator_stack", "renderer", "assets", "normalization"),
    "a" * 64,
)
SUITE = "libero_object"


def _case(kind, values, stop, recorded):
    return {
        "suite": SUITE,
        "task_id": "0",
        "kind": kind,
        "horizon": 2,
        "goal_spec_sha256": "b" * 64,
        "recorded_success": recorded,
        "samples": [
            {
                "step": step,
                "state": {"object_in_target": value},
                "native_success": value,
                "stop_reason": stop if step == len(values) - 1 else None,
            }
            for step, value in enumerate(values)
        ],
    }


def _report():
    return build_evaluator_report(
        model="smolvla",
        runtime=RUNTIME,
        goal_checker_sha256="c" * 64,
        fixtures=[
            _case("goal_unmet", [False], None, None),
            _case("goal_reached", [False, True, False], "horizon", True),
            _case("horizon_timeout", [False, False, False], "horizon", False),
        ],
        check_goal=lambda suite, task, goal, state: state["object_in_target"],
    )


def _plan(*, condition=None):
    metadata = {"suite": SUITE}
    if condition is not None:
        metadata["condition"] = condition
    attempts = (PlannedAttempt(AttemptKey("run", "task", "pair", "condition", "attempt"),
                               task_seed=1, policy_seed=2, metadata=metadata),)
    protocol = {"P": {"experiment": {"refinement_v3": {
        "stage": "confirmation",
        "model": "smolvla",
        "runtime": RUNTIME,
        "evaluator_horizons": {SUITE: 2},
    }}}}
    digest = _plan_digest(
        "run", attempts, paired_schedule=(), source_spec_sha256=None, protocol=protocol
    )
    return FrozenCampaignPlan("run", attempts, digest, protocol=protocol)


def _bundle(directory, plan, report):
    def write(name, value):
        data = json.dumps(value).encode()
        (directory / f"{name}.json").write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    write("runtime", RUNTIME)
    return write("approval", {
        "schema": "benchstudio.refinement_v3_approval.v1",
        "plan_digest_sha256": plan.plan_digest_sha256,
        "evidence": {
            "engineering_preflight": write("engineering_preflight", {"passed": True}),
            "evaluator": write("evaluator", report),
        },
    })


class EvaluatorQualificationTests(unittest.TestCase):
    def test_qualification_accepts_transient_success_and_timeout(self):
        plan = _plan()
        report = _report()
        self.assertTrue(report["passed"], report["issues"])
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            approval = _bundle(directory, plan, report)
            self.assertEqual(
                verify_refinement_qualification(plan, directory, approval), "smolvla"
            )

    def test_gate_rechecks_evidence_even_with_an_approved_digest(self):
        for fault in ("native_signal", "missing_case", "horizon", "bare_pass"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                plan = _plan()
                report = _report()
                if fault == "native_signal":
                    report["cases"][2]["samples"][-1]["native_success"] = True
                elif fault == "missing_case":
                    report["cases"].pop()
                elif fault == "horizon":
                    report["cases"][2]["horizon"] = 1
                else:
                    report = {"passed": True}
                approval = _bundle(directory, plan, report)
                with self.assertRaisesRegex(ValueError, "evaluator qualification failed"):
                    verify_refinement_qualification(plan, directory, approval)

    def test_gate_rejects_attempt_horizon_different_from_qualification(self):
        plan = _plan(condition={"max_episode_steps": 3})
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            approval = _bundle(directory, plan, _report())
            with self.assertRaisesRegex(ValueError, "different evaluator horizon"):
                verify_refinement_qualification(plan, directory, approval)
