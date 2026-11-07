# Evaluate Python systems

Use callable models, world models or complete agent workflows with Python objects.
This example uses arithmetic functions; it downloads no model and runs no simulator.

```python
import benchstudio as bs

system = bs.System.from_callable(
    lambda x: x * 2, name="example-system", revision="implementation-r1"
)
benchmark = bs.Benchmark(
    name="arithmetic", revision="dataset-r1",
    inputs=[1, 2], targets=[2, 4],
    scorer=lambda prediction, target: bs.Score(success=prediction == target),
    evaluator_revision="exact-match-r1",
)
evaluator = bs.pipeline("system-evaluation", system=system, benchmark=benchmark)
results = evaluator()
print([trial.success for trial in results.trials])
```

Construction is inert; calling the evaluator executes the supplied Python code.
A world-model scorer can return `bs.Score(metrics={"mse": value})` without
inventing a binary success criterion. An agent callable can own an entire
multi-component workflow. Use a full `SystemSpec` with `bs.System(runtime, spec)`
when component and connection identity matters.

The runtime owns reset, state isolation and cleanup. This first execution path
is sequential and propagates runtime/scoring exceptions. It does not yet provide
automatic checkpoint loading, batching, distributed scheduling or resumable
execution. Reuse the benchmark for comparisons and pin its revision to the
dataset, ordering and scoring definition. Identities are caller declarations,
not proof of dataset contents or runtime execution. Inputs should be treated
as immutable; the same object instances are passed to the callable.

Scores default to `authoritative=False`. Set authority explicitly only when
the evaluator is qualified for the intended comparison. Successful execution
does not establish task success. JSON is an interchange format; no JSON file
is required to construct or run this API.

## Analyze saved evidence

```python
import benchstudio as bs

reference = bs.open_run("runs/reference-system")
candidate = bs.open_run("runs/candidate-system")
comparison = bs.compare_system_runs(reference, candidate)
print(comparison.paired_success.to_dict())
```

This analyzes independently scored evidence and **does not load models,
run environments, or fabricate success**.

Run the synthetic illustration after package installation:

```bash
python examples/systems/composite_ablation.py
```

## Import existing Inspect Robots evaluations

RoboCurve already has an excellent runtime for evals on real/sim robots,
including LLM agents, VLAs, graders, run logs, re-scoring and Rerun. Rather
than replace that execution stack, BenchStudio can import its `EvalLog`
v3 data when the experimenter provides *missing scientific identity*:

```python
run = bs.import_inspect_robots(
    "inspect-log.json", system=my_system,
    task_revision="v1", protocol_digest="a"*64,
    evaluator_revision="r1", environment_revision="isaac-v1",
    seed_by_scene={"scene-0": 42},
    condition="nominal", score_key="success_at_end",
    trust_grader=False,
)
```

The default `trust_grader=False` means imported records are **not**
authorized for formal binary success comparisons. The caller must explicitly
establish grader authority, interpretation and provenance. Fractional scores
remain continuous metrics, never silently rounded to success/failure.

A real Inspect Robots log does not necessarily encode a multi-component
SystemSpec, matching seed mapping or protocol identity. This is a conservative
adapter, NOT proof of such metadata. Qualify the adapter on retained real logs
before using it for published comparisons.

Inspect Robots source schema reviewed: EvalLog v3 in
https://github.com/robocurve/inspect-robots/blob/main/src/inspect_robots/log.py
