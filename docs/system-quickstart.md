# System-level research quickstart

BenchStudio can evaluate an **entire composed system** represented by a
versioned graph of components (world models, agents, WAMs, policies, tools).

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
