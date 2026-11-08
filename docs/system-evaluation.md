# Evaluate a system

The canonical task is `evaluate`, shared by `bs.pipeline()` and `benchstudio evaluate`.
Use the single `evaluate` task through `bs.pipeline(system=..., benchmark=...)` and
`Benchmark.load(...)`. There are no task-name or loader aliases.

The researcher supplies a System, a Benchmark and an EvaluationConfig. The same
EvaluationEngine performs requirement checks, scalar/batched/async execution,
independent scoring and evidence retention for both Python and the CLI.

```python
import benchstudio as bs

system = bs.System.from_callable(lambda x: 2 * x, name="example", revision="r1")
benchmark = bs.Benchmark(
    "arithmetic", "data-r1", inputs=[1, 2], targets=[2, 4],
    scorer=lambda output, target: bs.Score(success=output == target),
    evaluator_revision="exact-r1",
)
evaluation = bs.pipeline(
    system=system, benchmark=benchmark,
    config=bs.EvaluationConfig(run_id="example", output_dir="runs/example"),
)
check = evaluation.check()  # configuration + installed dependency metadata only
results = evaluation.run()
print(results.summary())
retained = bs.open_run("runs/example")
```

This self-contained example executes arithmetic, not a learned model. Authority
remains false unless the benchmark explicitly declares it. Existing output
folders are refused before runtime execution. Choose a new output for a new run;
there is no hidden retry or automatic resume. With output_dir=None, results remain
in memory; results.save(path) explicitly retains them in the same evidence format.

## Installed systems and benchmarks

A backend package can provide a composed agent system, world model or robotics
adapter. Researchers select it by installed name, not by Python source filename:

```python
import benchstudio as bs

system = bs.System.from_backend("team.swarm", revision="system-commit")
benchmark = bs.Benchmark.load("team.task", revision="dataset-and-scorer-commit")
evaluation = bs.pipeline(
    system=system, benchmark=benchmark,
    config=bs.EvaluationConfig(run_id="comparison", output_dir="runs/comparison"),
)
print(evaluation.check())
results = evaluation.run()
```

team.swarm and team.task are illustrative installed plugin names, not bundled
benchmarks. No arbitrary repository code is downloaded or guessed. Missing or
ambiguous entry points and returned identity mismatches fail explicitly.
There is no universal checkpoint loader. Configure a model or composed system
with its own native API, then bind its callable with `System.from_callable`, or
install a named system backend that implements its own input/action contract.

Backend authors register trusted factories in their package's pyproject.toml:

```toml
[project.entry-points."benchstudio.systems"]
"team.swarm" = "team_package:make_system"

[project.entry-points."benchstudio.benchmarks"]
"team.task" = "team_package:make_benchmark"
```

The system factory returns bs.System; the benchmark factory returns bs.Benchmark.
Both receive revision and must preserve the requested identity. Factories should
be lightweight; defer heavy runtime/model construction to execution. Loading an installed factory executes trusted package
code, so BenchStudio cannot guarantee third-party factories are side-effect-free.
No extra script is required from the researcher using an installed recipe.

A runtime may declare requirements={"distribution-name": "exact-version"} (or
None for any installed version). `check()` inspects distribution metadata without
importing those dependencies. Missing or mismatched requirements stop execution
before the runtime/model loader. This
checks the controlling Python environment; an external-process backend owns its
native-interpreter, assets, renderer and checkpoint verification. BenchStudio does
not silently install packages or rewrite existing environments.

A runtime can declare supports_async=False. Batch capability is its existing
generate_batch(inputs) method. Async execution uses arun(); batch_size is used by
run(). Concurrency requires independently managed state per trial. Cooperative
async cancellation cannot interrupt blocking Python or native kernels.

## Same configuration, same execution from the CLI

```sh
benchstudio evaluate --system team.swarm --system-revision system-commit \
  --benchmark team.task --benchmark-revision dataset-and-scorer-commit \
  --run-id comparison --output runs/comparison --check

benchstudio evaluate --system team.swarm --system-revision system-commit \
  --benchmark team.task --benchmark-revision dataset-and-scorer-commit \
  --run-id comparison --output runs/comparison
```

Use `--batch-size` for batched runtimes, or `--async --concurrency N --timeout S`
for cooperative async systems. The CLI constructs the same System, Benchmark and
EvaluationConfig as Python. Specialized robotics and campaign interfaces retain
their own scientific accounting; they are separate from generic system trials.

## Retained results and interpretation

output_dir contains the existing system.json, trials.jsonl and manifest.json
format, plus execution.json with the configuration and declared system/benchmark
identities. The output directory is reserved before work starts. An execution
exception propagates and records execution_failed; no scientific outcome is
invented. A missing manifest makes partial output unreadable as a completed run.
open_run verifies evidence file hashes before returning results.

`check().configuration_valid` is static configuration validation, not native qualification;
check().native_verified stays false. Installed dependency metadata and declared
revisions do not prove checkpoint integrity, simulator determinism, correct action
units, evaluator validity or scientific release. Those remain properties of the
native backend and experimental protocol. This change does not authorize or run
Warren's E0, parity checks or R22/R25 confirmation campaign.


For the actual Refinement/Refresh operator status and division of work, see
[the Warren handoff](refinement-operator-status.md). Generic installed-backend
examples do not imply that SmolVLA or pi0.5 recipes are already installed.
