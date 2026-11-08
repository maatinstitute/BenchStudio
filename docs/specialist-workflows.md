# Specialist workflows

For the supported API, start with [the API guide](research-preview.md). These workflows are specialized and require their documented inputs and runtime dependencies.

# BenchStudio

BenchStudio is a research-use source-available library for experimental evaluation of AI systems,
especially interactive and embodied systems. The unit under evaluation is an
executable system: a model, a composed predictor/planner/controller, a group of
agents, or a complete robotics episode adapter.

Python objects configure systems and benchmarks. Versioned evidence formats
support storage and interoperability. Backends own execution semantics; the
benchmark owns its scoring definition. Comparisons preserve that distinction.

## Offline evaluation: predictions and components

```python
import benchstudio as bs
from benchstudio.analysis.claims import ClaimType
from benchstudio.replay_worker import ReplayLimits
from benchstudio.preparation import SourcePackage, check_imports

system = bs.System.from_callable(lambda x: 2*x, name="example", revision="r1")
benchmark = bs.Benchmark(
    "arithmetic", "fixtures-r1", inputs=[1, 2], targets=[2, 4],
    scorer=lambda output, target: bs.Score(success=output == target),
    evaluator_revision="exact-match-r1",
)
evaluation = bs.pipeline(
    system=system, benchmark=benchmark,
    config=bs.EvaluationConfig(run_id="example", output_dir="runs/example"),
)
print(evaluation.check().summary())
results = evaluation()
print(results.summary())
retained = bs.open_run("runs/example")
```

This executes arithmetic functions, not a learned model or simulator. Evaluator
authority defaults to false. Native adapters, checkpoints, state reset and
benchmark qualification still need explicit setup. For researcher-owned inference, configure native objects or endpoints and bind
their callables as described in [Native systems](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/native-systems.md). No
provider-specific model loader is maintained in the core package. Installed
systems and benchmark recipes resolve by name through
`System.from_backend` and `Benchmark.load`. The [system evaluation
guide](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/system-evaluation.md) covers the shared Python/CLI engine, dependency
checks, result retention and backend packaging. Native qualification remains a
separate requirement.

Use [paired system experiments](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/paired-system-experiments.md) to construct
an executable Workflow, replace a named component and compare variants through
`bs.pipeline("ablation", ...)`. The complete synthetic example is
`python examples/systems/paired_ablation.py`. Async execution and agent groups
are described in [async system execution](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/async-system-execution.md).
Declared component isolation alone does not establish a causal effect.

## Configure components using their native APIs

Configure a VLA policy, world model, agent workflow, inference engine or service
client directly using its own API.
BenchStudio does not insert inference defaults or maintain a mirror of its options:

```python
import benchstudio as bs

system = bs.System.from_callable(
    configured_system_function, name="candidate", revision="full-setup-r1",
    configuration=declared_setup,
)
print(system.describe())
evaluation = bs.pipeline(system=system, benchmark=benchmark, config=config)
results = evaluation()
```

The native function and its parameters remain under the researcher's control.
The optional declaration is visible and retained with results; omitted settings
are labeled opaque. It does not configure or certify the actual system. Any model
framework can be configured by its owner; native observations, actions and
predictions are preserved. See
[working native-object and endpoint patterns](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/native-systems.md).

## Complete interactive evaluations

An evaluation of LIBERO or AlpaSim is a calendar of episodes/scenes, conditions and
repetitions, not one policy prediction. Executable benchmarks bind that calendar
to native execution, outcomes and aggregation using the same engine. See
[benchmark protocols](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/benchmark-protocols.md) for experimental units versus
native execution groups, coverage, retention and the current LIBERO boundary.

## Installed simulator integrations

Installed integrations use the same callable pipeline and shared configuration:

```python
import benchstudio as bs

evaluation = bs.pipeline(
    "alpasim", model="route_following", alpasim_root="/opt/alpasim",
    scene_ids=("YOUR_INSTALLED_SCENE_ID",),
    config=bs.EvaluationConfig(output_dir="runs/alpasim", timeout=900),
)
print(evaluation.benchmark.describe())
print(evaluation.check().summary())
results = evaluation()
print(results.summary())
```

This requires the optional AlpaBridge integration and a provisioned native stack;
configuration checks do not qualify that stack. See [the integration guide](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/alpabridge-migration.md).
The researcher does not implement a backend, manage a worker or call per-case
methods. Integration authors have a separate [extension contract](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/execution-backends.md).

## Robotics evaluation pipeline

The robotics evaluation pipeline accepts task, model, environment, seeds and
evaluation conditions directly for registered robotics adapters:

```python
import benchstudio as bs

run = bs.pipeline(
    "robotics-evaluation",
    task={"id": "pick-cube", "revision": "fixture-v1"},
    model="mock",
    environment={"adapter": "mock-simulator", "kind": "simulator"},
    seeds=[7, 8],
    conditions=[{"id": "baseline"}],
    run_id="first-evaluation",
    output_dir="runs/first-evaluation",
    execution="mock",
)()
print(run.summary())
print(run.analyze().summary())
```

This is a synthetic API check. It does not load a robot policy or establish
simulator fidelity. Run the checked-in version with a fresh output directory:

```bash
python examples/direct_pipeline_mock.py runs/first-evaluation
```

The result separates execution accounting (`run.summary()`) from offline
evidence review (`run.analyze()`). BenchStudio freezes the named inputs into a
campaign plan and records its digest. Stable task revisions, checkpoint
identities, seeds, conditions, and environment configuration remain explicit
because they define what an evaluation means.

## Connect a real policy and environment

For a stack already supported through registered adapters, replace the mock
declarations with those adapters and set `execution="registry"`:

```python
import benchstudio as bs

evaluation = bs.pipeline(
    "robotics-evaluation",
    task={"id": "libero/spatial/task-0", "revision": "<pinned-task-revision>"},
    model={
        "adapter": "smolvla",
        "checkpoint": "sha256:<reviewed-checkpoint-digest>",
        "config": {"command": ["python", "your_policy_service.py"]},
    },
    environment={
        "adapter": "external_command",
        "id": "libero-local",
        "config": {"command": ["python", "your_environment_service.py"]},
    },
    seeds=[7, 8],
    conditions=[{"id": "baseline", "denoising_steps": 10}],
    run_id="smolvla-libero-baseline",
    output_dir="runs/smolvla-libero-baseline",
    execution="registry",
)
run = evaluation()
print(run.summary())
```

The named policy and environment adapters must already be installed and their
services must implement the JSON-line protocols documented by those adapters.
This is not an automatic Transformers-style checkpoint loader: the caller owns
the robot observation/action mapping, preprocessing, environment assets, and
runtime installation. See [the API comparison](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/transformers-comparison.md)
for the exact boundary and [the model bridge example](https://github.com/amtellezfernandez/BenchStudio/blob/main/examples/external_runtime/lerobot_smolvla_policy.py)
for a LeRobot-owned SmolVLA process.

To inspect an existing run without executing it again:

```python
import benchstudio as bs

audit = bs.pipeline(
    "campaign-audit", claim_type=ClaimType.SINGLE_RUN_OUTCOME
)("runs/first-evaluation")
print(audit.summary())
```

## Developer quick start

```bash
python -m pytest
benchstudio campaign --episodes 3 --output runs/smoke
```

Inspect optional backend and model-adapter readiness before scheduling work:

```bash
benchstudio campaign --readiness
```

Install an optional Genesis backend only in the environment that owns its
runtime:

```bash
python -m pip install 'benchstudio[genesis]'
```

The Genesis adapter requires explicit scene, action, and observation callbacks;
BenchStudio does not infer task controllers or claim Genesis scoring authority.

Verify an existing run artifact offline, optionally against a digest held by
an independent reviewer or CI system:

```bash
benchstudio campaign --verify-artifact runs/smoke \
  --trusted-manifest-sha256 <manifest-sha256>
```

Signed manifests can be verified with `--manifest-signature` and
`--trusted-public-key` instead of, or in addition to, the digest reference.

Verify a retained source snapshot against a local source checkout:

```bash
python scripts/verify_source_snapshot.py \
  docs/source-snapshots/alpabridge-27c96e6.json \
  /path/to/AlpaBridge
```

The command checks every listed file digest and rejects missing, changed, or
path-escaping entries. It does not require the historical upstream commit to
remain reachable.

Audit canonical RoboChallenge observe-only records without interpreting their
opaque payloads or claiming task success:

```bash
benchstudio campaign --robochallenge-records robochallenge.jsonl \
  --robochallenge-output robochall