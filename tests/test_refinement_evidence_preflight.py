"""scripts/validate_refinement_evidence.py against synthetic Protocol E evidence.

`protocol_e_exporter_synthetic.json` was produced by the unmodified Protocol E exporter
(`evaluator_validation.benchstudio_report`, refinement-refresh-robot-policies PR #5 @ 3b4a78e) from
synthetic rows: four suites, horizon 6, synthetic hashes. It is the handoff contract under test, not
evidence about any native stack.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchstudio.campaigns.frozen_plan import (
    AttemptKey,
    FrozenCampaignPlan,
    PlannedAttempt,
    _plan_digest,
)

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/validate_refinement_evidence.py"
CAPTURE = ROOT / "examples/external_runtime/native_runtime_capture_py38.py"
EXPORT = json.loads((Path(__file__).parent / "protocol_e_exporter_synthetic.json").read_text())
SUITES = ("libero_spatial", "libero_object", "libero_goal", "libero_10")
HORIZONS = {suite: 6 for suite in SUITES}
SYNTHETIC_GL = {"vendor": "SYNTHETIC", "renderer": "SYNTHETIC", "version": "SYNTHETIC"}


def _h(*parts):
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def _plan(horizons=HORIZONS, model="pi0.5", runtime=None):
    attempts = tuple(
        PlannedAttempt(
            AttemptKey("run", f"t{i}", "p", "c", f"a{i}"),
            task_seed=1,
            policy_seed=2,
            metadata={"suite": suite},
        )
        for i, suite in enumerate(sorted(horizons))
    )
    protocol = {
        "P": {
            "experiment": {
                "refinement_v3": {
                    "stage": "confirmation",
                    "model": model,
                    "runtime": runtime or EXPORT["runtime"],
                    "evaluator_horizons": horizons,
                }
            }
        }
    }
    digest = _plan_digest(
        "run", attempts, paired_schedule=(), source_spec_sha256=None, protocol=protocol
    )
    return FrozenCampaignPlan("run", attempts, digest, protocol=protocol).to_dict()


def _run(*argv):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, argv)], capture_output=True, text=True, check=False
    )
    return proc.returncode, json.loads(proc.stdout)


def _write(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
    return path


def _evaluator(tmp_path, report, plan=None):
    plan_path = _write(tmp_path, "plan.json", plan if plan is not None else _plan())
    report_path = _write(tmp_path, "evaluator.json", report)
    return _run("evaluator", "--plan", plan_path, "--evaluator", report_path)


def _case(report, kind, suite="libero_spatial"):
    return next(c for c in report["cases"] if c["kind"] == kind and c["suite"] == suite)


# ---- evaluator mode ---------------------------------------------------------------------------


def test_exporter_output_passes_matching_plan(tmp_path):
    code, out = _evaluator(tmp_path, EXPORT)
    assert (code, out["issues"]) == (0, [])
    assert "not launch-gate equivalent" in out["scope"]


def test_one_suite_report_passes_one_suite_plan(tmp_path):
    report = copy.deepcopy(EXPORT)
    report["cases"] = [c for c in report["cases"] if c["suite"] == "libero_spatial"]
    code, out = _evaluator(tmp_path, report, _plan({"libero_spatial": 6}))
    assert (code, out["issues"]) == (0, [])


def test_one_suite_report_fails_four_suite_plan(tmp_path):
    report = copy.deepcopy(EXPORT)
    report["cases"] = [c for c in report["cases"] if c["suite"] == "libero_spatial"]
    code, out = _evaluator(tmp_path, report)
    assert code == 1
    assert sum("missing cases" in issue for issue in out["issues"]) == 3


def test_four_suite_report_fails_one_suite_plan(tmp_path):
    code, out = _evaluator(tmp_path, EXPORT, _plan({"libero_spatial": 6}))
    assert code == 1
    assert out["issues"] and all("unexpected suite" in issue for issue in out["issues"])


def _mutated(mutate):
    report = copy.deepcopy(EXPORT)
    mutate(report)
    return report


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda r: r.update(schema="benchstudio.evaluator_qualification.v2"), "schema or model"),
        (lambda r: r.update(model="smolvla"), "schema or model"),
        (lambda r: r["cases"][0].update(suite="libero_90"), "unexpected suite"),
        (lambda r: _case(r, "horizon_timeout").update(horizon=7), "horizon does not match"),
        (
            lambda r: _case(r, "horizon_timeout")["samples"][2].update(native_success=True),
            "native success disagrees",
        ),
        (
            lambda r: _case(r, "goal_reached")["samples"][4].update(native_success=False),
            "native success disagrees with independent goal at step 4",
        ),
        (lambda r: r.update(cases=r["cases"][:-1]), "missing cases"),
        (lambda r: _case(r, "goal_reached").update(samples=[]), "uninterrupted trace"),
        (lambda r: _case(r, "goal_reached")["samples"][1].pop("goal_met"), "invalid evidence"),
        (
            lambda r: _case(r, "goal_reached").update(recorded_success=False),
            "recorded episode success disagrees",
        ),
        (lambda r: r.update(cases={}), "cases must be a list"),
        (lambda r: r.update(passed=False), "passed is not true"),
        (lambda r: r["runtime"].update(renderer=_h("other")), "runtime mismatch"),
    ],
)
def test_inconsistent_evidence_fails(tmp_path, mutate, needle):
    code, out = _evaluator(tmp_path, _mutated(mutate))
    assert code == 1, out
    assert any(needle in issue for issue in out["issues"]), out["issues"]


def test_missing_and_malformed_inputs_are_input_errors(tmp_path):
    plan = _write(tmp_path, "plan.json", _plan())
    assert _run("evaluator", "--plan", plan, "--evaluator", tmp_path / "absent.json")[0] == 2
    truncated = _write(tmp_path, "bad.json", json.dumps(EXPORT)[:-9])
    assert _run("evaluator", "--plan", plan, "--evaluator", truncated)[0] == 2
    tampered = _plan()
    tampered["protocol"]["P"]["experiment"]["refinement_v3"]["model"] = "smolvla"
    code, out = _evaluator(tmp_path, EXPORT, tampered)
    assert code == 2 and "digest does not match" in out["issues"][0]


def test_unexpected_exception_fails_closed(tmp_path):
    plan = _plan()
    plan["protocol"]["P"]["experiment"]["refinement_v3"]["evaluator_horizons"] = ["libero_spatial"]
    attempts = [
        PlannedAttempt(
            AttemptKey(**a["key"]),
            task_seed=a["task_seed"],
            policy_seed=a["policy_seed"],
            metadata=a["metadata"],
        )
        for a in plan["attempts"]
    ]
    plan["plan_digest_sha256"] = _plan_digest(
        "run", attempts, paired_schedule=(), source_spec_sha256=None, protocol=plan["protocol"]
    )
    code, out = _evaluator(tmp_path, EXPORT, plan)
    assert (code, out["verdict"]) == (3, "INTERNAL_ERROR")


def test_evidence_is_not_modified(tmp_path):
    plan = _write(tmp_path, "plan.json", _plan())
    report = _write(tmp_path, "evaluator.json", EXPORT)
    before = (report.read_bytes(), report.stat().st_mtime_ns, plan.read_bytes())
    _run("evaluator", "--plan", plan, "--evaluator", report)
    assert before == (report.read_bytes(), report.stat().st_mtime_ns, plan.read_bytes())


# ---- bundle mode (the launch gate, not launched) ----------------------------------------------


def _bundle(tmp_path, mutate=None, approval_sha=None):
    directory = tmp_path / "qualification"
    directory.mkdir()
    plan = _plan()
    files = {
        "runtime": copy.deepcopy(EXPORT["runtime"]),
        "evaluator": copy.deepcopy(EXPORT),
        "engineering_preflight": {"passed": True},
        "stock_parity": {"passed": True},
        "g02": {"passed": True},
    }
    if mutate:
        mutate(files)
    evidence = {}
    for name, value in files.items():
        data = json.dumps(value).encode()
        (directory / f"{name}.json").write_bytes(data)
        if name != "runtime":
            evidence[name] = hashlib.sha256(data).hexdigest()
    approval = json.dumps(
        {
            "schema": "benchstudio.refinement_v3_approval.v1",
            "plan_digest_sha256": plan["plan_digest_sha256"],
            "evidence": evidence,
        }
    ).encode()
    (directory / "approval.json").write_bytes(approval)
    plan_path = _write(tmp_path, "plan.json", plan)
    return _run(
        "bundle",
        "--plan",
        plan_path,
        "--qualification-directory",
        directory,
        "--approval-sha256",
        approval_sha or hashlib.sha256(approval).hexdigest(),
    )


def test_bundle_passes_with_exporter_output(tmp_path):
    code, out = _bundle(tmp_path)
    assert (code, out.get("qualified_model")) == (0, "pi0.5"), out


@pytest.mark.parametrize(
    ("mutate", "approval", "needle"),
    [
        (
            lambda f: _case(f["evaluator"], "horizon_timeout")["samples"][3].update(
                native_success=True
            ),
            None,
            "native success disagrees",
        ),
        (lambda f: f["runtime"].update(checkpoint=_h("x")), None, "observed runtime identities"),
        (
            lambda f: f["evaluator"].update(goal_checker_sha256=f["runtime"]["runner"]),
            None,
            "separate goal checker identity",
        ),
        (None, _h("not-the-approval"), "does not match the trusted digest"),
    ],
)
def test_bundle_failures(tmp_path, mutate, approval, needle):
    code, out = _bundle(tmp_path, mutate, approval)
    assert code == 1
    assert needle in out["issues"][0]


# ---- runtime mode with the Python 3.8 capture helper ------------------------------------------


def _helper():
    spec = importlib.util.spec_from_file_location("bs_capture_py38", CAPTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _capture(tmp_path):
    files = {}
    for group in ("runner", "checkpoint", "assets", "normalization"):
        path = tmp_path / f"{group}.bin"
        path.write_bytes(f"synthetic {group}".encode())
        files[group] = {f"{group}_file": path}
    _helper().capture_and_write(
        tmp_path / "capture",
        modules={"pytest": pytest},
        files=files,
        read_renderer=lambda: dict(SYNTHETIC_GL),
    )
    capture = json.loads((tmp_path / "capture/capture.json").read_text())
    return capture, tmp_path / "capture/runtime.json"


def _runtime(tmp_path, capture, runtime, *extra):
    path = _write(tmp_path, "c.json", capture)
    if isinstance(runtime, dict):
        runtime = _write(tmp_path, "r.json", runtime)
    return _run("runtime", "--capture", path, "--runtime", runtime, *extra)


def test_injected_renderer_is_not_runtime_evidence(tmp_path):
    capture, runtime = _capture(tmp_path)
    code, out = _runtime(tmp_path, capture, runtime, "--rehash-files")
    assert code == 1
    assert out["issues"] == ["renderer identity was injected, not read from a live GL context"]
    assert out["files_rehashed"] == 5


def test_capture_consistency_checks_pass_when_relabelled(tmp_path):
    capture, runtime = _capture(tmp_path)
    capture["renderer_source"] = "active_opengl_identity"  # test-only relabel
    code, out = _runtime(tmp_path, capture, runtime, "--rehash-files")
    assert (code, out["issues"]) == (0, [])


def test_hand_written_empty_capture_is_refused(tmp_path):
    capture, _ = _capture(tmp_path)
    bare = {
        "schema": capture["schema"],
        "stack": {},
        "renderer": {},
        "files": {},
        "renderer_source": "active_opengl_identity",
        "capture_module_sha256": capture["capture_module_sha256"],
    }
    nev = _helper().load_capture_module()
    bare["identity"] = {"simulator_stack": nev._digest({}), "renderer": nev._digest({})}
    code, out = _runtime(tmp_path, bare, bare["identity"])
    assert code == 1 and len(out["issues"]) == 4, out["issues"]


@pytest.mark.parametrize(
    ("edit", "needle"),
    [
        (lambda c: c.update(capture_module_sha256=_h("other")), "this checkout's"),
        (lambda c: c["stack"].update(python="3.12.0"), "not derivable"),
        (lambda c: c.update(resolved_file_paths={}), "no recorded path for file"),
    ],
)
def test_runtime_inconsistencies(tmp_path, edit, needle):
    capture, runtime = _capture(tmp_path)
    capture["renderer_source"] = "active_opengl_identity"
    edit(capture)
    code, out = _runtime(tmp_path, capture, runtime, "--rehash-files")
    assert code == 1
    assert any(needle in issue for issue in out["issues"]), out["issues"]


def test_runtime_json_must_equal_identity(tmp_path):
    capture, runtime = _capture(tmp_path)
    capture["renderer_source"] = "active_opengl_identity"
    other = json.loads(runtime.read_text())
    other["renderer"] = _h("other")
    code, out = _runtime(tmp_path, capture, other)
    assert "runtime.json differs from the capture's identity mapping" in out["issues"]
