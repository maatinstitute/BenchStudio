#!/usr/bin/env python3
"""Read-only preflight of Refinement v3 / Protocol E evidence with BenchStudio's own checks.

Modes:
  evaluator  evaluator.json against a frozen plan: evaluator_issues plus the launch gate's
             passed-is-true rule. Evaluator evidence only; NOT launch-gate equivalent.
  bundle     a whole qualification directory: verify_refinement_qualification, i.e. the launch
             gate itself, run without launching anything.
  runtime    capture.json + runtime.json from capture_native_runtime: the capture's own
             preconditions, the capture module hash, a live (not injected) renderer, the identity
             recomputed from the recorded inputs, and optionally a re-hash of every recorded file.

No check is re-implemented except the capture preconditions in `runtime`, which mirror
capture_native_runtime. Evidence is only read.

Exit codes: 0 PASS, 1 FAIL, 2 INPUT_ERROR, 3 INTERNAL_ERROR. Every nonzero code means not valid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path

PASS, FAIL, INPUT_ERROR, INTERNAL_ERROR = 0, 1, 2, 3
FILE_GROUPS = {"runner", "checkpoint", "assets", "normalization"}
IDENTITY_KEYS = FILE_GROUPS | {"simulator_stack", "renderer"}
GL_FIELDS = ("vendor", "renderer", "version")


class InputError(Exception):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> tuple[object, str]:
    path = Path(path)
    if not path.is_file():
        raise InputError(f"{label} not found: {path}")
    raw = path.read_bytes()
    try:
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    except ValueError as exc:
        raise InputError(f"{label} is not valid JSON ({exc}): {path}") from exc


def _load_plan(path: Path):
    from benchstudio.campaigns.frozen_plan import FrozenCampaignPlan

    payload, digest = _read_json(path, "plan")
    try:
        plan = FrozenCampaignPlan.from_dict(payload)
    except ValueError as exc:
        raise InputError(f"plan rejected: {exc}") from exc
    experiment = ((plan.protocol or {}).get("P") or {}).get("experiment") or {}
    declaration = experiment.get("refinement_v3")
    if not isinstance(declaration, dict):
        raise InputError("plan has no protocol.P.experiment.refinement_v3 declaration")
    for field in ("model", "runtime", "evaluator_horizons"):
        if field not in declaration:
            raise InputError(f"refinement_v3 declaration lacks {field}")
    return plan, declaration, digest


def _evaluator(args) -> tuple[list[str], dict]:
    from benchstudio.analysis.evaluator_qualification import evaluator_issues

    _, declaration, plan_sha = _load_plan(args.plan)
    report, report_sha = _read_json(args.evaluator, "evaluator report")
    if not isinstance(report, dict):
        raise InputError("evaluator report must be a JSON object")
    issues = list(
        evaluator_issues(
            report,
            model=declaration["model"],
            runtime=declaration["runtime"],
            horizons=declaration["evaluator_horizons"],
        )
    )
    if report.get("passed") is not True:
        issues.append("report field passed is not true")
    scope = "evaluator evidence only; not launch-gate equivalent (use bundle)"
    return issues, {"scope": scope, "plan_sha256": plan_sha, "evaluator_sha256": report_sha}


def _bundle(args) -> tuple[list[str], dict]:
    from benchstudio.campaigns.qualification import verify_refinement_qualification

    plan, _, plan_sha = _load_plan(args.plan)
    directory = Path(args.qualification_directory)
    if not directory.is_dir():
        raise InputError(f"qualification directory not found: {directory}")
    detail = {
        "scope": "launch gate (verify_refinement_qualification), not launched",
        "plan_sha256": plan_sha,
        "inputs": {p.name: _sha256_file(p) for p in sorted(directory.glob("*.json"))},
    }
    try:
        model = verify_refinement_qualification(plan, directory, args.approval_sha256)
    except ValueError as exc:
        return [str(exc)], detail
    return [], {**detail, "qualified_model": model}


def _capture_preconditions(capture: dict) -> list[str]:
    """Mirror of capture_native_runtime's own refusals."""
    issues = []
    modules = capture["stack"].get("modules")
    if not isinstance(modules, dict) or not modules:
        issues.append("capture lists no imported modules")
    groups = capture["files"]
    if set(groups) != FILE_GROUPS or any(not isinstance(g, dict) or not g for g in groups.values()):
        issues.append(
            f"capture must have exactly the four non-empty file groups {sorted(FILE_GROUPS)}"
        )
    renderer = capture["renderer"]
    if any(not isinstance(renderer.get(k), str) or not renderer[k].strip() for k in GL_FIELDS):
        issues.append("capture lacks a complete renderer identity")
    if set(capture["identity"]) != IDENTITY_KEYS:
        issues.append(f"capture identity must have exactly {sorted(IDENTITY_KEYS)}")
    return issues


def _rehash(capture: dict) -> tuple[list[str], int]:
    issues, checked = [], 0
    paths = capture.get("resolved_file_paths") or {}
    for group, names in capture["files"].items():
        for name, expected in names.items():
            path = (paths.get(group) or {}).get(name)
            if not path:
                issues.append(f"no recorded path for file {group}/{name}")
                continue
            checked += 1
            if not Path(path).is_file() or _sha256_file(Path(path)) != expected:
                issues.append(f"file {group}/{name} at {path} does not match the capture")
    module_paths = capture.get("resolved_module_paths") or {}
    for dist, record in (capture["stack"].get("modules") or {}).items():
        path = module_paths.get(dist)
        if not path:
            issues.append(f"no recorded path for module {dist}")
            continue
        checked += 1
        expected = record.get("imported_file_sha256") if isinstance(record, dict) else None
        if not Path(path).is_file() or _sha256_file(Path(path)) != expected:
            issues.append(f"module {dist} file at {path} does not match the capture")
    if checked == 0:
        issues.append("re-hash requested but no file could be checked")
    return issues, checked


def _runtime(args) -> tuple[list[str], dict]:
    from benchstudio.integrations import native_evaluator_evidence as nev

    capture, capture_sha = _read_json(args.capture, "capture")
    runtime, runtime_sha = _read_json(args.runtime, "runtime")
    if (
        not isinstance(capture, dict)
        or capture.get("schema") != "benchstudio.native_runtime_capture.v1"
    ):
        raise InputError("capture is not a benchstudio.native_runtime_capture.v1 document")
    for field in ("identity", "stack", "renderer", "files"):
        if not isinstance(capture.get(field), dict):
            raise InputError(f"capture lacks {field}")
    issues = _capture_preconditions(capture)
    module_sha = _sha256_file(Path(nev.__file__))
    if capture.get("capture_module_sha256") != module_sha:
        issues.append("capture was not made with this checkout's native_evaluator_evidence.py")
    if capture.get("renderer_source") != "active_opengl_identity":
        issues.append("renderer identity was injected, not read from a live GL context")
    recomputed = {
        "simulator_stack": nev._digest(capture["stack"]),
        "renderer": nev._digest(capture["renderer"]),
        **{group: nev._digest(hashes) for group, hashes in capture["files"].items()},
    }
    if recomputed != capture["identity"]:
        issues.append("capture identity is not derivable from its own stack/renderer/file records")
    if runtime != capture["identity"]:
        issues.append("runtime.json differs from the capture's identity mapping")
    checked = 0
    if args.rehash_files:
        more, checked = _rehash(capture)
        issues.extend(more)
    return issues, {
        "scope": "capture consistency; does not establish which code executed",
        "capture_sha256": capture_sha,
        "runtime_sha256": runtime_sha,
        "capture_module_sha256": module_sha,
        "files_rehashed": checked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    evaluator = sub.add_parser("evaluator")
    evaluator.add_argument("--plan", required=True, type=Path)
    evaluator.add_argument("--evaluator", required=True, type=Path)
    bundle = sub.add_parser("bundle")
    bundle.add_argument("--plan", required=True, type=Path)
    bundle.add_argument("--qualification-directory", required=True, type=Path)
    bundle.add_argument("--approval-sha256", required=True)
    runtime = sub.add_parser("runtime")
    runtime.add_argument("--capture", required=True, type=Path)
    runtime.add_argument("--runtime", required=True, type=Path)
    runtime.add_argument("--rehash-files", action="store_true")
    args = parser.parse_args(argv)
    handler = {"evaluator": _evaluator, "bundle": _bundle, "runtime": _runtime}[args.mode]
    try:
        issues, detail = handler(args)
        code = PASS if not issues else FAIL
        out = {
            **detail,
            "mode": args.mode,
            "verdict": "PASS" if code == PASS else "FAIL",
            "issues": issues,
        }
    except InputError as exc:
        code, out = INPUT_ERROR, {"mode": args.mode, "verdict": "INPUT_ERROR", "issues": [str(exc)]}
    except Exception as exc:  # fail closed on anything unexpected
        code = INTERNAL_ERROR
        out = {
            "mode": args.mode,
            "verdict": "INTERNAL_ERROR",
            "issues": [f"{type(exc).__name__}: {exc}"],
            "traceback": traceback.format_exc().splitlines()[-3:],
        }
    print(json.dumps(out, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
