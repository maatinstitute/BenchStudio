# A benchmark is an evaluation protocol, not one inference call

`Benchmark` supports two distinct execution modes through the same engine:

- Offline: existing inputs, targets and an independent scorer. This remains useful
  for predictions, saved-observation policy checks and dataset evaluation.
- Protocol: a complete experimental calendar plus native execution, outcome and
  aggregation rules. This is the appropriate unit for interactive suites such as
  LIBERO and AlpaSim. It does not turn a policy callback into a complete rollout.

The researcher configures the system using its native framework. A protocol
integration binds that system to an existing native benchmark runtime. That
integration is per environment/protocol, not one adapter per checkpoint/model.
Installed benchmark factories loaded through `Benchmark.load` can return either
mode without a second engine or an additional Experiment abstraction.

## Researcher experience

The existing AlpaBridge integration now constructs an executable Benchmark:

```python
import benchstudio as bs

evaluation = bs.pipeline(
    "alpasim", model="route_following", alpasim_root="/opt/alpasim",
    scene_ids=("YOUR_INSTALLED_SCENE_A", "YOUR_INSTALLED_SCENE_B"),
    environment_revision="YOUR_REVIEWED_NATIVE_STACK_REVISION",
    config=bs.EvaluationConfig(output_dir="runs/scene-study", timeout=900),
)
print(evaluation.benchmark.describe())   # the whole declared scene calendar
print(evaluation.check().summary())
results = evaluation()                  # explicit native execution
print(results.summary())
print(results.benchmark)                # retained plan, also available on reopening
```

This requires the optional AlpaBridge package and provisioned native stack.
Revisions are declarations, not automatically verified pins. AlpaBridge labels
its environment UNVERIFIED_NATIVE_ENVIRONMENT unless the operator supplies a
revision; `native_verified` remains false even after supplying one. No scientific
qualification or permission follows from construction, checks, hashes or merging.

For an installed complete protocol, the generic public flow is
`bs.pipeline(system=configured_system, benchmark=benchmark, config=config)` followed
by `evaluation()`. The configured system may be a native policy/client/architecture
object, not necessarily a scalar callable or a `bs.System`. Its protocol owns the
binding. Existing offline benchmarks still require their existing callable System.

## Experimental units and execution groups

A LIBERO-style study can have suite × task × initial state × seed × condition
units, each involving many policy calls and simulator steps. The native runner
may execute the entire reviewed calendar in one process to preserve its gates,
model reuse and original accounting. AlpaSim can instead dispatch one scene per
job, with native scene metrics aggregated afterward. Neither should be reduced
to one generic success trial or one model prediction.

Integration authors describe experimental units with
`benchstudio.backends.BenchmarkCase(case_id, dimensions, execution_id=None)`.
Dimensions retain the native suite/task/state identity, seed, condition, scene,
repetition or other protocol-defined axes. They are immutable declarations, not
new states or inferred physical equivalences. case_id must be unique across the
calendar; each attempt/condition unit needs its appropriate native identity.

`execution_id` groups units into native jobs. It defaults to case_id for one job
per unit. Multiple units can explicitly share a single native job. The bound
backend's execution IDs must match the calendar's ordered groups exactly; a mismatch
fails before worker startup. The engine does not split a native cohort into new
unapproved sub-runs or create scientific identities.

## Integration contract

The protocol exposes `cases`, `supports_retries` (default false), and
`bind(system, benchmark=..., config=...)`. Binding is configuration-only and returns
the existing ExecutionBackend. It must not load models, open simulators or allocate
workers. Native startup/cleanup, per-job execution and reports use the existing
backend lifecycle. Outcome definitions, termination, horizon, action/observation
semantics, missingness, coverage and aggregation remain in that native protocol.

```python
benchmark = bs.Benchmark(
    "my-native-study", "reviewed-protocol-revision",
    evaluator_revision="reviewed-evaluator-revision",
    environment_revision="reviewed-native-stack-revision",
    protocol=installed_protocol,
)
evaluation = bs.pipeline(system=configured_system, benchmark=benchmark, config=config)
```

An executable protocol cannot also supply offline inputs/targets/scorer. Its
outcomes retain native identities and formats; `Benchmark.key()` does not
manufacture offline scorer rows for them. The offline `authoritative=True` flag is
refused on protocol benchmarks; native evaluator authority remains native. Complete protocol/evaluator/environment
references are required as declarations. No mandatory physical-AI task schema is
imposed on agent systems or other interactive benchmarks.

## Retention and interpretation

The engine reserves a fresh output directory and writes `benchmark.json` before
native startup. It records the full planned calendar, group mapping, revisions,
explicit retry policy and protocol digest. `execution.json` distinguishes planned
benchmark-case counts from native execution-group counts. Each `cases.jsonl`
receipt links an execution ID to its **planned_benchmark_case_ids**.

A completed execution receipt means only that the native job completed
operationally. It does not establish that all planned experimental outcomes were
observed. The native result/analysis must report actual coverage and missingness.
No missing per-unit outcome is fabricated, and native results are not pooled or
converted into a single task-success Boolean. A clean native batch audit is also
separate from task success and scientific qualification.

Protocol retries are refused unless the frozen protocol policy explicitly permits
them, even if generic EvaluationConfig.max_retries is positive. The policy is
captured when constructing the benchmark; later mutation does not expand it.
Existing native single-use, release and consumption guards remain authoritative.
The library adds no authorization, state generation, reserved population or retry
permission for the paper's confirmation campaign.

## Evidence and current limits

AlpaBridge is connected to this complete-benchmark route. Its existing scene
execution/metrics/audits remain native; the retained plan exposes the collection
instead of presenting it as a scalar model call. Optional revision arguments are
also available in its installed CLI.

A synthetic LIBERO-shaped test exercises paired condition/state/task axes, repeated
policy calls per unit, one grouped native execution, individual-unit dispatch,
partial outcome coverage and refusal of inherited retries. It does not import
LIBERO, generate states, qualify either model or provide a new runnable LIBERO
integration. Wiring the scientific paper runner to a protocol must preserve its
existing permissions and native instrumentation; those have not been replaced.
The published native LIBERO readiness blockers remain outstanding.

No simulator, learned model, GPU, E0 or scientific campaign was executed by this
change. Backend execution remains sequential; concurrency, batching of native jobs
and distributed resource allocation are not added here.
