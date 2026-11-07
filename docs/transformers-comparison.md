# Public API comparison: BenchStudio and Transformers

The API is designed for a Python user familiar with Transformers: import the
package as `bs`, choose a task, call its pipeline, and inspect a structured
result. BenchStudio cannot hide environment and checkpoint setup when those are
owned by external robot-learning runtimes, so a campaign document supplies
those explicit inputs.

## Run a declared robotics evaluation

The short path is to select the task pipeline, point it at a campaign, and call
it:

```python
import benchstudio as bs

evaluation = bs.pipeline(
    "robotics-evaluation",
    campaign="examples/campaigns/mock-worldepisode.json",
    output_dir="runs/first-evaluation",
    execution="mock",
)
run = evaluation()
print(run.summary())
```

The included mock campaign is a smoke check only. For actual evaluation, use
`execution="registry"` and declare the policy adapter, environment adapter,
checkpoint identity, task revision, seeds, and conditions in the campaign file.
BenchStudio validates that frozen declaration, executes its registered
adapters, and returns run accounting plus paths to the saved artifacts. It does
not guess which checkpoint, environment, or success scorer to use.

Analysis is separate, so the execution step does not silently turn run
accounting into a scientific claim:

```python
import benchstudio as bs

audit = bs.pipeline(
    "campaign-audit",
    claim_type=bs.ClaimType.SINGLE_RUN_OUTCOME,
)("runs/first-evaluation")
print(audit.summary())
```

## What maps to Transformers

| Transformers concept | BenchStudio equivalent |
| --- | --- |
| Task string | Pipeline task, such as `robotics-evaluation` or `campaign-audit` |
| Pipeline object | Callable configured task |
| Model/configuration inputs | Frozen campaign declaration with model and environment adapters |
| Inference output | Run receipt and persisted campaign evidence |
| Task-specific post-processing | Explicit campaign audit and analysis functions |

This is the same discovery pattern, adapted to experiments. A campaign is a
scientific execution specification, not a model identifier. It keeps versions,
conditions, and seeds visible and digest-bound.

## What BenchStudio deliberately does not infer

Transformers can often download a named model and its tokenizer because the
library owns or understands those model interfaces. BenchStudio's policy and
simulator runtimes are often installed and maintained separately. The API
therefore does not pretend that a model name alone identifies the full robot
stack.

- Installing an optional runtime remains an explicit environment step.
- Model and environment adapters must be declared and pass their capability
  checks before execution.
- Physical execution requires its separate protocol and authorization controls.
- The mock quickstart is not evidence of model or simulator validity.
- The campaign audit reads saved artifacts; it does not rerun an experiment or
  certify that the scientific design is valid.

The intended result is familiar ergonomics with inspectable experimental
inputs, rather than a one-line call with hidden defaults.
