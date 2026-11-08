# Preparing native programs

BenchStudio can verify an external program's declared source files before starting
its entry point, and check imports in a separate native Python environment. These
APIs apply to robotics, models and agent systems. Neither API creates scientific
qualification, grants execution permission or accesses a consumption registry.

```python
import benchstudio as bs

sources = bs.SourcePackage.from_directory(
    "./experiment", files=["scripts/benchmark.py", "scripts/helpers.py"]
)
report = sources.verify()       # reads and hashes sources; does not import them
archive_sha256 = sources.archive("./experiment-sources.tar.gz")
```

`from_directory` records the files you explicitly select. Creating a snapshot
establishes a baseline; it does not establish that the selected code is correct or
approved. No checkpoint, package environment or undeclared dependency is bundled.
The deterministic archive contains those files and `SOURCE_MANIFEST.json`, using
the existing `benchstudio_source_snapshot_v1` format. Its digest is independent of
source timestamps and the archive filename. Existing outputs are refused.

For an existing reviewed manifest:

```python
sources = bs.SourcePackage.from_manifest("./SOURCE_MANIFEST.json", root="./experiment")
print(sources.verify())

# Only when this particular execution is appropriate/authorized:
receipt = sources.run(
    "scripts/benchmark.py",
    python="/path/to/native/bin/python",
    args=("--config", "/path/to/config"),
    log_dir="./logs/first-run",
    timeout=600,
)
```

`run` verifies every declared file again, then starts the declared Python entry
point through `bs.ProcessCommand`. On a missing or mismatched file it raises
`bs.SourceVerificationError` before spawning the child. On success it retains the
source verification report, stdout/stderr and exit receipt. A failed process or
timeout raises `bs.ProcessFailure`; no automatic retry is introduced. Every run
needs a new log directory. The child's working directory is the source root.

These are trusted-host integrity checks, not a sandbox or protection from a
concurrent writer. Keep the source tree immutable throughout execution. Files that
can affect execution must be included deliberately; verification cannot discover
arbitrary imports or pin dependencies, assets, checkpoints and renderer behavior
for you. Protocol-specific validators remain responsible for those checks.

## Independent import diagnostics

```python
import benchstudio as bs

report = bs.check_imports(
    "robosuite",                    # explicitly requested native import
    python="/path/to/client/bin/python",
    log_dir="./logs/import-check",
    timeout=60,
)
print(report["imports"])            # actual origins and versions
```

BenchStudio starts a temporary clean working directory and invokes Python with
`-I`. Current-directory modules, `PYTHONPATH` and user-site packages are excluded;
packages installed in the selected interpreter's environment remain available.
The probe supports Python 3.8+ even though the controlling BenchStudio process
requires Python 3.10+. A missing module, import exception or `SystemExit(0)` raised
inside an imported module is a failed check with a nonzero exit. The report and
process logs are retained on failure. The API raises `bs.ProcessFailure` and does
not certify native readiness from the process exit alone.

An import executes the installed module's top-level code; there is no guarantee
that third-party imports are side-effect-free. BenchStudio does not construct an
environment, load a checkpoint or launch an episode itself. This is an explicit
diagnostic and not a substitute for native protocol qualification. Isolated
import success also does not certify a different command's import paths.

## Existing staging manifests

`SourcePackage.from_manifest` also reads the legacy `all_files_sha256` mapping in
`STAGE_MANIFEST.json`, so operators can verify an existing staged directory without
rewriting its manifest or rehashing an authorization artifact. The generic verifier
does not interpret `bound`, `approved_by`, or protocol-specific scope fields.

For the already staged Refinement/Refresh E0 package, retain its existing pins and
single-use permission. This API is for subsequent reviewed workflows; introducing
it does not require restaging that package, change the permission, or validate
Warren's separate pre-launch verifier. The scientific driver still owns its
specific authorization and consumption checks.

## One execution API

Source verification is part of `bs.ProcessCommand` and applies to commands,
services and direct process contexts through the same pre-spawn path:

```python
import benchstudio as bs

sources = bs.SourcePackage.from_manifest("STAGE_MANIFEST.json", root="./staged")
command = bs.ProcessCommand(
    "experiment",
    ("/path/to/native/bin/python", "/absolute/path/to/staged/scripts/benchmark.py"),
    cwd=sources.root,
    sources=sources,
)
receipt = command.run("./logs/experiment")
```

`SourcePackage.run` remains a Python-entry-point convenience method that delegates
to this execution API. Packaging and import diagnostics do not implement a second
runner. The CLI calls these same APIs. Source verification reports are retained as
`<command-name>.sources.json` beside the command logs.

## One command line

The installed command is `benchstudio`. Its subcommands are `run`, `verify`,
`package`, `doctor` and `evaluate`. `benchstudio evaluate` uses the existing
evaluation parser; the older `benchstudio-run` entry point stays compatible.
Calling `benchstudio` without arguments prints help and executes nothing.

After installing this BenchStudio version in the controlling Python environment,
use `benchstudio` (or `python -m benchstudio`). No user-written
Python or shell wrapper is needed.

```sh
benchstudio verify --manifest /path/to/STAGE_MANIFEST.json --root /path/to/staged
benchstudio doctor --python /path/to/native/bin/python --log-dir /path/to/import-logs robosuite
```

A single launch can include an explicitly permitted import diagnostic:

```sh
benchstudio run \
  --manifest /path/to/STAGE_MANIFEST.json --root /path/to/staged \
  --python /path/to/native/bin/python --entrypoint scripts/benchmark.py \
  --log-dir /path/to/new-logs --check-import robosuite \
  -- --config /path/to/config
```

All declared source hashes are checked before the import diagnostic; failure stops
the sequence. The native entry point is launched only after the diagnostic passes
and all hashes are checked again. Arguments after `--` are passed literally to
the existing entry point. Its task-specific guards remain in force.

### Existing Warren E0 package

This wrapper can verify the unchanged 48-file package before its existing
`protocol_e0.py` loads the harness. A separate external pre-launch verifier is not
required when using this route. Install BenchStudio in a **separate controlling
Python >=3.10 environment**, leaving the staged BenchStudio/harness files and
Python 3.8 client intact.

Only once the existing E0 authorization artifact and required host-side checks
are complete, the operator command has this form (replace the stage/auth/output
paths with their actual retained locations):

```sh
MUJOCO_GL=osmesa benchstudio run \
  --manifest /path/to/STAGE_MANIFEST.json --root /path/to/staged \
  --python /home/warren/alba-cross-policy-20261101/envs/client/bin/python \
  --entrypoint benchstudio/docs/refinement-v3-e0/protocol_e0.py \
  --log-dir /path/to/new-e0-launch-logs \
  -- \
  --harness-dir experiments/tooling/cross_policy_v3 \
  --fixtures benchstudio/docs/refinement-v3-e0/e0_fixtures_pi05.json \
  --document benchstudio/docs/refinement-v3-e0/README.md \
  --authorisation /path/to/existing/E0_AUTH.json \
  --ledger /home/warren/e0-registry --output /path/to/new-e0-output
```

This invokes the existing E0 driver, including its original consumption checks,
without editing the staged files or authorization. No new E0 permission, retry,
import-diagnostic permission or campaign release is created by this command.
If the ledger shows prior consumption, retain it and stop. Separate NC1 refusal
checks are still the existing protocol's responsibility; this wrapper does not
turn a plumbing result into evaluator qualification.

The source-only archive can likewise be produced without a packaging script:
`benchstudio package --manifest STAGE_MANIFEST.json --root /path/to/staged --output sources.tar.gz`.
