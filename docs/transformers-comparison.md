# Public API comparison: BenchStudio and Transformers

The public API follows the familiar Transformers pattern: import as `bs`,
choose a task, configure a callable pipeline, and inspect a structured result.
For a robot evaluation, the task, policy adapter, environment adapter,
checkpoint identity, conditions, and seeds are explicit inputs.

## Configure a task pipeline

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
)
run = evaluation()
print(run.summary())
```

The adapter services must implement their declared protocols and own their
runtime dependencies. BenchStudio checks registered adapter readiness, freezes
the inputs into a campaign plan, and executes through its evidence ledger.
Callers can supply the equivalent campaign as JSON/YAML when they need less
common protocol fields.

The checked-in mock quickstart is also available and runs without model or
simulator dependencies. It verifies the Python path only; it is not evidence
about model quality or simulator fidelity.

Analysis stays explicit:

```python
import benchstudio as bs

audit = bs.pipeline(
    "campaign-audit",
    claim_type=bs.ClaimType.SINGLE_RUN_OUTCOME,
)("runs/smolvla-libero-baseline")
print(audit.summary())
```

## What maps to Transformers

| Transformers concept | BenchStudio equivalent |
| --- | --- |
| Task string | Pipeline task, such as `robotics-evaluation` or `campaign-audit` |
| Pipeline object | Callable configured task |
| Model and tokenizer arguments | Model adapter, pinned checkpoint, and adapter config |
| Input text or media | Versioned robot task and environment adapter |
| Inference output | Run receipt and persisted campaign evidence |
| Task-specific post-processing | Explicit campaign audit and analysis functions |

A campaign is an experiment specification, not a model identifier. Its task
revision, seeds, conditions, environment, and model identity stay explicit and
digest-bound for reproducibility.

## Differences BenchStudio must preserve

Transformers can often download a named model and its tokenizer because the
library owns or understands those model interfaces. BenchStudio's policy and
simulator runtimes are often installed and maintained separately. It does not
pretend that a model name alone identifies the full robot stack.

- Optional runtime installation remains an explicit environment step.
- Model and environment adapters must pass readiness and capability checks.
- Physical execution remains subject to its separate protocol and authorization
  controls.
- A run summary reports execution accounting; it is not itself a scientific
  claim.
- A campaign audit reads saved artifacts; it does not rerun an experiment or
  certify that the scientific design is valid.

The API makes common workflows discoverable without requiring readers to learn
the internal campaign compiler or the research paper first.
