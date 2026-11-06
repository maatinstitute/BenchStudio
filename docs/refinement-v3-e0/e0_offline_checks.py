"""Offline checks of protocol_e0.py gates and verdicts. Not collected by BenchStudio's pytest run.

Needs the refinement-refresh-robot-policies harness (PR #5 @ 3b4a78e) because protocol_e0.py calls
it unchanged:

    HARNESS_DIR=<checkout>/experiments/tooling/cross_policy_v3 \
        python3 -m unittest docs/refinement-v3-e0/e0_offline_checks.py

The native driver (`run_fixture_pi05`) and host checks are stubbed: nothing imports LIBERO, MuJoCo
or OpenPI. The stub raises the harness's literal ISO message, asserted against the harness source.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), os.environ["HARNESS_DIR"]]
import evaluator_validation as EV  # noqa: E402
import protocol_e0 as E0  # noqa: E402
import release  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def h(*parts):
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


class E0Gates(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.fixtures = HERE / "e0_fixtures_pi05.json"
        self.document = HERE / "README.md"
        self.calls = []
        self.original = EV.run_fixture_pi05

    def tearDown(self):
        EV.run_fixture_pi05 = self.original

    def write(self, name, value):
        path = self.dir / name
        path.write_text(json.dumps(value))
        return path

    def auth(self, scope=E0.SCOPE, document=None, fixtures=None, drop=None):
        bound = {name: sha(path) for name, path in E0.gate_chain(EV).items()}
        bound["fixtures"] = sha(fixtures or self.fixtures)
        bound["protocol_e0.py"] = sha(E0.__file__)
        if drop:
            del bound[drop]
        return self.write("auth.json", {"approved_by": "Alba", "scope": scope, "bound": bound,
                                        "document_sha256": sha(document or self.document)})

    def stub(self, nc2=True, message=E0.NC2_MESSAGE, agree=True, constant=False, crash=None):
        def driver(fixture, root, forbidden):
            self.calls.append((fixture["fixture_id"], sorted(forbidden)))
            if crash:
                raise crash
            if forbidden and nc2:
                raise EV.EvaluatorIncident(message)
            n = 20 if fixture["expected_case"] == "GOAL_UNMET" else 220
            trace = [{"step": i, "recorded_success": (not agree) and i == 5,
                      "independent_goal": False, "episode_ended": False} for i in range(n)]
            samples = [{"state_sha256": h("c") if constant else h("s", i)} for i in range(n + 1)]
            meta = {"bddl_sha256": h("bddl"), "goal_atoms": [["on", "a", "b"]],
                    "benchstudio_samples": samples}
            return trace, 220, meta

        EV.run_fixture_pi05 = driver

    def args(self, auth, output="out", fixtures=None):
        return types.SimpleNamespace(fixtures=str(fixtures or self.fixtures),
                                     document=str(self.document), authorisation=str(auth),
                                     ledger=str(self.dir / "ledger"), output=str(self.dir / output))

    def run_e0(self, args, host=None):
        def host_ok(fixture):
            return {"official_state_sha256": h("official-state-0")}

        return E0.run(args, EV, release, host=host or host_ok)

    def test_stub_uses_the_harness_message(self):
        literal = 'EvaluatorIncident("{}")'.format(E0.NC2_MESSAGE)
        self.assertIn(literal, Path(EV.__file__).read_text())

    def test_pass_path(self):
        self.stub()
        record = self.run_e0(self.args(self.auth()))
        self.assertEqual(record["verdict"], "E0_PLUMBING_PASS_NC1_PENDING")
        self.assertEqual(self.calls[0], ("E0_pi05_spatial_t0_unmet", [h("official-state-0")]))
        self.assertIn("release.py", record["inputs_sha256"])

    def test_outputs_tagged_non_counting(self):
        self.stub()
        self.run_e0(self.args(self.auth()))
        for path in (self.dir / "out").iterdir():
            if path.name != "e0_record.json":
                self.assertTrue(path.name.endswith((".e0trace.json", ".e0samples.json")))
                document = json.loads(path.read_text())
                self.assertEqual((document["non_counting"], document["scope"]), (True, E0.SCOPE))

    def test_second_execution_refused(self):
        self.stub()
        auth = self.auth()
        self.run_e0(self.args(auth))
        with self.assertRaises(E0.E0Refused):
            self.run_e0(self.args(auth, output="out2"))

    def test_authorisation_gates_refuse_before_any_work(self):
        self.stub()
        for auth in (self.dir / "absent.json", self.auth(scope="PROTOCOL_E_PI05"),
                     self.auth(document=EV.PROTOCOL_E_DOCUMENT), self.auth(drop="release.py")):
            with self.assertRaises(SystemExit):
                self.run_e0(self.args(auth))
        self.assertEqual(self.calls, [])
        self.assertFalse((self.dir / "out").exists())

    def test_fixture_changes_refused(self):
        document = json.loads(self.fixtures.read_text())
        document["fixtures"][1]["action_source"]["steps"] = 50
        changed = self.write("fx.json", document)
        with self.assertRaises(EV.FixtureError):
            self.run_e0(self.args(self.auth(fixtures=changed), fixtures=changed))

    def test_failure_verdicts(self):
        cases = [({"nc2": False}, "E0_FAIL"), ({"message": "other incident"}, "E0_FAIL"),
                 ({"agree": False}, "E0_FAIL"), ({"constant": True}, "E0_FAIL"),
                 ({"crash": ImportError("libero")}, "UNINTERPRETABLE")]
        for i, (stub, verdict) in enumerate(cases):
            self.stub(**stub)
            record = self.run_e0(self.args(self.auth(), output="out{}".format(i)))
            self.assertEqual(record["verdict"], verdict, stub)
            (self.dir / "ledger").rename(self.dir / "ledger{}".format(i))

    def test_host_mismatch_fails_before_fixtures(self):
        self.stub()

        def wrong_host(fixture):
            raise E0.E0Refused("LIBERO checkout is not the pinned revision")

        record = self.run_e0(self.args(self.auth()), host=wrong_host)
        self.assertEqual((record["verdict"], self.calls), ("E0_FAIL", []))


if __name__ == "__main__":
    unittest.main()
