# Refinement v3: Protocol E evidence handoff

This page covers how Protocol E evaluator evidence moves from the native harness into BenchStudio, and what checks it on the way. **No native experiment has been run** for any of it. No LIBERO, MuJoCo, OpenPI, model or GPU process was started. Every result below comes from synthetic data.

## Execution and validation stay separate

| Step | Program | Where |
|---|---|---|
| Execute Protocol E and record per-step evidence | `experiments/tooling/cross_policy_v3/evaluator_validation.py` (refinement-refresh-robot-policies, PR #5 @ `3b4a78e`) | native env; Python 3.8 for the π0.5 client |
| Export `evaluator.json` (`benchstudio.evaluator_qualification.v1`) | `evaluator_validation.benchstudio_report` (same file) | same process; never imports BenchStudio |
| Capture the runtime identity | `examples/external_runtime/native_runtime_capture_py38.py` (this PR), which calls `capture_native_runtime` unchanged | inside the native process |
| Validate before any launch | `scripts/validate_refinement_evidence.py` (this PR) | Python ≥ 3.10 |
| Validate at launch | `campaigns/qualification.py::verify_refinement_qualification` (unchanged) | `benchstudio-run` |

No BenchStudio-native launcher is added. The harness keeps E-AUTH, ISO and the counted-run rule. BenchStudio stays out of the execution path.

## Preflight: `scripts/validate_refinement_evidence.py`

```sh
python scripts/validate_refinement_evidence.py evaluator --plan plan.json --evaluator evaluator.json
python scripts/validate_refinement_evidence.py bundle --plan plan.json \
    --qualification-directory QUAL --approval-sha256 <digest from the approver>
python scripts/validate_refinement_evidence.py runtime --capture capture.json --runtime runtime.json \
    [--rehash-files]
```

- **evaluator mode:** `evaluator_issues` plus the gate's `passed is True` rule, against a frozen plan (`FrozenCampaignPlan.from_dict`, digest checked). Its output says "evaluator evidence only; not launch-gate equivalent".
- **bundle mode:** `verify_refinement_qualification` itself, so the launch gate runs without launching.
- **runtime mode:**
  - checks the capture against `capture_native_runtime`'s own preconditions;
  - requires `capture_module_sha256` to equal this checkout's `native_evaluator_evidence.py`;
  - refuses `renderer_source: injected`;
  - recomputes the identity with `_digest`;
  - checks `runtime.json` equals it;
  - optionally re-hashes every recorded file and module file, failing closed on a missing path.
- **Exit codes:** 0 pass; 1 issues; 2 missing or malformed input or a rejected plan; 3 unexpected exception. The tool only reads.

No validation rule is changed or re-implemented. The only mirrored logic is the capture preconditions.

## Python 3.8 runtime capture

`import benchstudio` fails on Python 3.8: `measurement.py` subscripts `collections.abc.Callable` at import, and the package declares `requires-python >=3.10`. The helper therefore reads `native_evaluator_evidence.py` once, hashes those bytes, and executes the same bytes as a standalone module. It then calls `capture_native_runtime` unchanged and records `capture_module_sha256` and `renderer_source`. Without a live GL context it raises rather than fabricating a renderer.

Tested on CPython 3.8.20 with synthetic inputs (`tests/test_native_runtime_capture_py38.py`, enabled by `BENCHSTUDIO_PYTHON38`). **Not yet run in the OpenPI client environment**, so whether PyOpenGL and a current OSMesa context are available at the capture point there is unknown.

It is not yet wired into the harness. Until `evaluator_validation.py` calls it after the env is built, the runtime file passed to the exporter is operator-attested.

## What the runtime identity establishes

| Key | Covers | Does not cover |
|---|---|---|
| `simulator_stack` | Python version/implementation, OS, kernel, arch; per listed module: `__version__`, installed version, sha256 of `__file__` | the rest of a package (a package's `__init__.py` only), compiled extensions, the interpreter binary (path recorded, not hashed) |
| `renderer` | GL vendor/renderer/version of the current context | which process rendered |
| `runner`, `checkpoint`, `assets`, `normalization` | sha256 of each file the caller lists | whether a listed file was executed or loaded |

π0.5 runs two processes: the client steps the env, and the server (Python 3.11) loads the checkpoint. The identity covers the process that captures it.

## `runtime.runner` and provenance

The gate requires `runtime.json == plan runtime == evaluator.json.runtime`, so a single `runner` digest has to describe both the Protocol E run and the confirmation run.

**Proposed convention:** both processes list the same `runner` group, the files of the whole v3 execution chain:
- `client_openpi.py`, `common.py` (frozen v2);
- `evaluator_validation.py`, `runner_v2.py`, `adapter_pi05.py`, `classify.py`, `attestation.py`, `release.py`, `qualification.py`, `v3common.py`.

`runner` then means "these files, byte for byte, were present in both captures". That is what the gate's equality can certify.

The program that produced the evidence is recorded in `protocol_e_record.json` (`harness_sha256`), linked to `evaluator.json` through `protocol_e_results_sha256`.

Limits the schema cannot express:
- **Producer vs presence.** Nothing in `evaluator.json` names the producing program.
- **Checker separation.** The goal checker (`goal_checker_sha256`) and the fixture driver are one file. The independence is the protocol's E4 design, not separate programs. `goal_checker_sha256 != runtime.runner` cannot detect this.
- **Model-free `checkpoint`.** In a model-free run, `checkpoint` describes files present on the host, not anything the evaluator used.

## Suite coverage

The exporter emits all four suites because Protocol E requires 12 fixtures. `evaluator_issues` expects exactly the plan's suites. Tested: a 4-suite export passes a 4-suite plan, and a 1-suite report passes a 1-suite plan. Mixed pairs fail with "missing cases" or "unexpected suite". This is consistent behaviour, not a schema gap. The supported combination for v3 is 4 suites against a 4-suite plan.

## Test results (this branch, local)

| Run | Result |
|---|---|
| Full suite, Python 3.12.13, `PYTHONPATH=src pytest -q` | 792 passed, 6 skipped, **7 failed**. The same 7 fail on `main` @ `46f65b1` in this environment (756 passed there), all `ModuleNotFoundError: cryptography`, the optional `signing` extra |
| New tests (`test_refinement_evidence_preflight.py`, `test_native_runtime_capture_py38.py`) | 36 passed, including the Python 3.8.20 subprocess test |
| `tests/test_ci_smoke.py`; `compileall src tests examples scripts` | pass |
| `docs/refinement-v3-e0/e0_offline_checks.py` against the PR #5 harness, Python 3.12 and 3.8.20 | 8/8 each |
| ruff (repo config) on the new Python files | clean. The repository as a whole reports existing findings, unchanged |

The exporter fixture `tests/protocol_e_exporter_synthetic.json` was produced by the unmodified PR #5 exporter from synthetic rows (horizon 6). It pins the handoff contract and is not evidence about any stack. An earlier, broader offline pass on the exporter side (45 adversarial cases, 16 mutation checks, one blind AI review whose findings are addressed here) is summarised in the PR description.

## E0

`docs/refinement-v3-e0/` holds a proposed non-counting plumbing run for the π0.5 stack: the specification, the exact fixture file, the program (`protocol_e0.py`, which targets the refinement harness), and its offline checks. It is not authorised and has not run. Two protocol questions decide whether it can (see that README).
