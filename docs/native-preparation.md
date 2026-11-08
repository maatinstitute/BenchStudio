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
