#!/usr/bin/env python3
"""E0: non-counting plumbing run of the Protocol E harness, pi0.5 only. NEVER RUN. Python 3.8.

E0 is a PROPOSED ADDENDUM to 13_EVALUATOR_VALIDATION.md and needs Alba's approval as such
(docs/refinement-v3-e0/README.md lists the three rules it adds). It is kept apart from the counted
Protocol E run by construction:
  - authorisation scope PROTOCOL_E0_PI05, bound to docs/refinement-v3-e0/README.md (neither scope
    opens the other);
  - single use: the first execution under an authorisation consumes it (ledger marker, written
    before any native import); a second execution is refused;
  - every output file is wrapped and tagged non_counting, with E0-only suffixes; no BenchStudio
    export exists;
  - the result is E0_PLUMBING_PASS_NC1_PENDING / E0_FAIL / UNINTERPRETABLE, never an evaluator
    verdict.
It calls the PR #5 harness functions unchanged (validate_fixtures, run_fixture_pi05, compare) and
PR #5's release.check_authorisation, with the whole gate chain (release.py, v3common.py,
client_openpi.py, common.py, launch_guard.py) bound into the authorisation.

    protocol_e0.py --harness-dir experiments/tooling/cross_policy_v3 \
        --fixtures e0_fixtures_pi05.json --document README.md --authorisation E0_AUTH.json \
        --ledger LEDGER_DIR --output NEW_DIR
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

SCOPE = "PROTOCOL_E0_PI05"
LIBERO_REVISION = "f78abd68ee283de9f9be3c8f7e2a9ad60246e95c"  # OpenPI 215abfb third_party/libero
INIT_FILE_SHA256 = (
    "cbbc73792ce546c9bec181fd328a411d3183074840b282671dee481511381d0a"  # libero_spatial task 0
)
NC2_MESSAGE = (
    "fixture state collides with a confirmation state"  # evaluator_validation.run_fixture_pi05
)
EXPECTED = {
    "E0_pi05_spatial_t0_unmet": {
        "suite": "libero_spatial",
        "task_id": 0,
        "expected_case": "GOAL_UNMET",
        "action_source": {"kind": "scripted_noop", "steps": 20},
    },
    "E0_pi05_spatial_t0_horizon": {
        "suite": "libero_spatial",
        "task_id": 0,
        "expected_case": "HORIZON",
        "action_source": {"kind": "scripted_noop", "steps": "horizon"},
    },
}
OFFICIAL_STATE = {"source": "official", "index": 0}


class E0Refused(RuntimeError):
    pass


def load_harness(harness_dir):
    sys.path.insert(0, str(Path(harness_dir).resolve()))
    import evaluator_validation as EV  # noqa: E402  PR #5, unchanged
    import release  # noqa: E402  PR #5, unchanged

    return EV, release


def gate_chain(EV):
    """Files whose behaviour the E0 gates and driver depend on; all bound into the authorisation."""
    v3 = Path(EV.__file__).resolve().parent
    v2 = v3.parent / "cross_policy"
    files = {
        "evaluator_validation.py": v3 / "evaluator_validation.py",
        "release.py": v3 / "release.py",
        "v3common.py": v3 / "v3common.py",
        "client_openpi.py": v2 / "client_openpi.py",
        "common.py": v2 / "common.py",
        "launch_guard.py": v2 / "launch_guard.py",
    }
    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        raise E0Refused("gate-chain files missing: {}".format(missing))
    return files


def check_fixtures(EV, document, root):
    EV.validate_fixtures(document, "pi05", root)  # PR #5 rules first
    fixtures = document["fixtures"]
    if sorted(f["fixture_id"] for f in fixtures) != sorted(EXPECTED):
        raise E0Refused("E0 takes exactly the fixtures {}".format(sorted(EXPECTED)))
    for fixture in fixtures:
        for key, value in EXPECTED[fixture["fixture_id"]].items():
            if fixture.get(key) != value:
                raise E0Refused("{}: {} must be {!r}".format(fixture["fixture_id"], key, value))
        if fixture.get("initial_state") != OFFICIAL_STATE:
            raise E0Refused(
                "{}: initial_state must be official index 0".format(fixture["fixture_id"])
            )
    return fixtures


def host_facts(fixture):
    """Native side: pinned host checks and the environment record. E0Refused on mismatch."""
    import libero.libero as libero_pkg
    import numpy as np
    from libero.libero import benchmark, get_libero_path

    suite = benchmark.get_benchmark_dict()[fixture["suite"]]()
    task = suite.get_task(fixture["task_id"])
    init_file = Path(get_libero_path("init_states")) / task.problem_folder / task.init_states_file
    init_sha = hashlib.sha256(init_file.read_bytes()).hexdigest()
    root = Path(libero_pkg.__file__).resolve().parents[1]
    try:
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=20,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = None
    versions = {}
    for name in ("robosuite", "mujoco", "numpy"):
        try:
            versions[name] = str(__import__(name).__version__)
        except Exception as error:  # recorded, not fatal: the pinned checks below are the gate
            versions[name] = "unavailable: {}".format(type(error).__name__)
    state = suite.get_task_init_states(fixture["task_id"])[fixture["initial_state"]["index"]]
    facts = {
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "MUJOCO_GL": os.environ.get("MUJOCO_GL"),
        "libero_root": str(root),
        "libero_revision": revision,
        "task_name": task.name,
        "init_file": str(init_file),
        "init_file_sha256": init_sha,
        "official_state_sha256": hashlib.sha256(np.asarray(state).tobytes()).hexdigest(),
        "versions": versions,
        "renderer_strings": "not captured: the harness driver opens and closes the env",
    }
    if revision != LIBERO_REVISION:
        raise E0Refused("LIBERO checkout {} is not the pinned {}".format(revision, LIBERO_REVISION))
    if init_sha != INIT_FILE_SHA256:
        raise E0Refused(
            "init-state file sha256 {} is not the pinned {}".format(init_sha, INIT_FILE_SHA256)
        )
    return facts


def e0_verdict(nc2_fired, results, nc4):
    if (
        not nc2_fired
        or len(results) != 2
        or not all(r["agrees"] for r in results)
        or not all(nc4.values())
    ):
        return "E0_FAIL"
    return "E0_PLUMBING_PASS_NC1_PENDING"


def write_tagged(EV, path, fixture_id, kind, data):
    EV.atomic_write_json(
        path,
        {
            "non_counting": True,
            "scope": SCOPE,
            "fixture_id": fixture_id,
            "kind": kind,
            "data": data,
        },
    )


def run(args, EV, release, host=host_facts):
    document = json.loads(Path(args.fixtures).read_text("utf-8"))
    root = Path(args.fixtures).resolve().parent
    fixtures = check_fixtures(EV, document, root)
    bound = dict(gate_chain(EV), fixtures=Path(args.fixtures), **{"protocol_e0.py": Path(__file__)})
    # E-AUTH before any native import, ledger or output: the counted run's function,
    # with E0's own scope and document.
    auth = release.check_authorisation(args.authorisation, Path(args.document), bound, scope=SCOPE)
    ledger = Path(args.ledger)
    ledger.mkdir(parents=True, exist_ok=True)
    marker = ledger / "{}.e0_started".format(auth["authorisation_sha256"])
    try:
        with open(
            str(marker), "x"
        ) as stream:  # single use: conservative burn, before any native work
            json.dump({"scope": SCOPE, "output": str(args.output)}, stream)
    except FileExistsError:
        raise E0Refused(
            "this E0 authorisation was already used ({}); a new one is required".format(marker)
        )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    record = {
        "schema": "protocol_e0_record_v1",
        "non_counting": True,
        "scope": SCOPE,
        "authorisation": auth,
        "ledger_marker": str(marker),
        "inputs_sha256": {k: EV.file_sha(v) for k, v in sorted(bound.items())},
        "document_sha256": EV.file_sha(Path(args.document)),
        "nc1": "PENDING: operator refusal transcripts are reviewed separately",
    }
    by_id = {f["fixture_id"]: f for f in fixtures}
    try:
        facts = host(by_id["E0_pi05_spatial_t0_unmet"])
        record["host"] = facts
        planted = facts["official_state_sha256"]  # NC2: plant the official state's own hash
        try:
            EV.run_fixture_pi05(by_id["E0_pi05_spatial_t0_unmet"], root, {planted})
            nc2_fired, nc2_detail = False, "no incident raised"
        except EV.EvaluatorIncident as incident:
            nc2_fired, nc2_detail = str(incident) == NC2_MESSAGE, str(incident)
        record["nc2"] = {"fired": nc2_fired, "detail": nc2_detail, "planted_sha256": planted}
        results, nc4 = [], {}
        for fixture_id in sorted(EXPECTED):
            fixture = by_id[fixture_id]
            trace, horizon, meta = EV.run_fixture_pi05(
                fixture, root, set()
            )  # E0 ISO: official states only
            result = dict(
                EV.compare(trace, fixture["expected_case"], horizon),
                fixture_id=fixture_id,
                bddl_sha256=meta["bddl_sha256"],
                goal_atoms=meta["goal_atoms"],
            )
            nc4[fixture_id] = len({s["state_sha256"] for s in meta["benchstudio_samples"]}) >= 2
            write_tagged(
                EV, output / "{}.e0trace.json".format(fixture_id), fixture_id, "trace", trace
            )
            write_tagged(
                EV,
                output / "{}.e0samples.json".format(fixture_id),
                fixture_id,
                "samples",
                meta["benchstudio_samples"],
            )
            results.append(result)
        record.update(
            results=results, nc4_state_advances=nc4, verdict=e0_verdict(nc2_fired, results, nc4)
        )
    except E0Refused as error:
        record.update(verdict="E0_FAIL", error="host check: {}".format(error))
    except (EV.EvaluatorIncident, EV.FixtureError) as error:
        record.update(verdict="E0_FAIL", error=repr(error))
    except Exception as error:  # env build/import failure: no interpretable outcome
        record.update(verdict="UNINTERPRETABLE", error=repr(error))
    EV.atomic_write_json(output / "e0_record.json", record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description="E0 non-counting Protocol E plumbing run (pi0.5)")
    for name in (
        "--harness-dir",
        "--fixtures",
        "--document",
        "--authorisation",
        "--ledger",
        "--output",
    ):
        parser.add_argument(name, required=True)
    args = parser.parse_args(argv)
    EV, release = load_harness(args.harness_dir)
    try:
        record = run(args, EV, release)
    except (E0Refused, EV.FixtureError) as error:
        print(json.dumps({"verdict": "REFUSED", "error": str(error)}))
        return 2
    except SystemExit as refused:  # release.Refused subclasses SystemExit (PR #5 release.py:17)
        print(json.dumps({"verdict": "REFUSED", "error": str(refused)}))
        return 2
    print(json.dumps({"verdict": record["verdict"], "non_counting": True, "nc1": "PENDING"}))
    return 0 if record["verdict"] == "E0_PLUMBING_PASS_NC1_PENDING" else 1


if __name__ == "__main__":
    sys.exit(main())
