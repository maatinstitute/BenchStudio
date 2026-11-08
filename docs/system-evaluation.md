# Evaluate a system

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
    "system-evaluation", system=system, benchmark=benchmark,
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
benchmark = bs.Benchmark.from_pretrained("team.task", revision="dataset-and-scorer-commit")
evaluation = bs.pipeline(
    "system-evaluation", system=system, benchmark=benchmark,
    config=bs.EvaluationConfig(run_id="comparison", output_dir="runs/comparison"),
)
print(evaluation.check())
results = evaluation.run()
```

team.swarm and team.task are illustrative installed plugin names, not bundled
benchmarks. No arbitrary repository code is downloaded or guessed. Missing or
ambiguous entry points and returned identity mismatches fail explicitly.
System.from_pretrained(model_id, revision=full_commit, backend="vllm") retains the
existing lazy upstream vLLM integration. Other pretrained backend names resolve
through the installed system entry-point group with model/revision/generation
options forwarded to their factory. There is no universal VLA/WAM checkpoint
loader: those backends must implement their own native input/action contract.

Backend authors register trusted factories in their package's pyproject.toml:

```toml
[project.entry-points."benchstudio.systems"]
"team.swarm" = "team_package:make_system"

[project.entry-points."benchstudio.benchmarks"]
"team.task" = "team_package:make_benchmark"
```

The system factory returns bs.System; the benchmark factory returns bs.Benchmark.
Both receive revision and must preserve the requested identity. Factories should
be lightweight; defer heavy runtime/model construction to execution, as the
built-in vLLM backend does. Loading an installed factory executes trusted package
code, so BenchStudio cannot guarantee third-party factories are side-effect-free.
No extra script is required from the researcher using an installed recipe.

A runtime may declare requirements={"distribution-name": "exact-version"} (or
None for any installed version). check() inspects distribution metadata without
importing those dependencies. vLLM declares its supported exact version. Missing
or mismatched requirements stop execution before the runtime/model loader. This
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

Use --backend vllm with --system model_id for the built-in pretrained text path.
Use --batch-size for batched runtimes, or --async --concurrency N --timeout S for
cooperative async systems. The CLI constructs the same System, Benchmark and
EvaluationConfig and calls the same pipeline as Python. It has no parallel runner.
The existing benchstudio-run command retains the legacy campaign CLI. Existing
robotics-evaluation/campaign APIs remain compatibility paths with their own
scientific accounting; they are not reinterpreted as generic system trials.

## Retained results and interpretation

output_dir contains the existing system.json, trials.jsonl and manifest.json
format, plus execution.json with the configuration and declared system/benchmark
identities. The output directory is reserved before work starts. An execution
exception propagates and records execution_failed; no scientific outcome is
invented. A missing manifest makes partial output unreadable as a completed run.
open_run verifies evidence file hashes before returning results.

check().configuration_valid is static compatibility, not native qualification;
check().native_verified stays false. Installed dependency metadata and declared
revisions do not prove checkpoint integrity, simulator determinism, correct action
units, evaluator validity or scientific release. Those remain properties of the
native backend and experimental protocol. This change does not authorize or run
Warren's E0, parity checks or R22/R25 confirmation campaign.
