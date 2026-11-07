# Public API comparison: BenchStudio and Transformers

This comparison was checked against the official Transformers repository and
installation guide on 7 November 2026:

- [Transformers pipeline implementation](https://github.com/huggingface/transformers/tree/main/src/transformers/pipelines)
- [Transformers installation guide](https://huggingface.co/docs/transformers/main/installation)
- [Transformers repository](https://github.com/huggingface/transformers)

## Patterns worth adopting

Transformers offers a short import, a task-oriented factory, a callable object,
a clear installation path, task-specific examples, and lazy resolution of the
selected task implementation. BenchStudio should make those same common actions
easy to discover and call.

The proposed public first path follows that shape:

```python
import benchstudio as bs

review = bs.pipeline("campaign-audit")
result = review("./runs/completed-campaign")
print(result.summary())
```

The task currently supported is an **offline audit of an existing campaign
directory**. It validates the saved plan, ledger, manifests, and runtime
receipts. It does not replay robot motion, start a simulator, load a checkpoint,
or infer task success from opaque artifacts. A summary is convenient display;
the structured `result.to_dict()` remains the machine-readable interface.

## Differences BenchStudio must preserve

Transformers is a model-loading and inference library. BenchStudio is an
evaluation and evidence library with external policy and simulator runtimes.
Matching Transformers' ergonomics does not mean copying its model registry or
claiming that the prerequisites of those external runtimes disappear.

For that reason:

- Tasks should be named for the operation they actually perform. An archived
  campaign audit is not called a replay.
- Model and simulator adapters must continue to declare their environment and
  capability requirements explicitly.
- Optional backends must not load merely because a user imports the core
  package or invokes an unrelated task.
- A task is not exposed through `pipeline()` until its inputs, dependencies,
  outputs, and execution boundary have tests and a runnable guide.
- The root package should expose a small supported API. Internal analysis
  primitives can remain available under specialist namespaces without all of
  them being advertised as stable.

## Current gap to close

Only `campaign-audit` is implemented in the initial public factory. Before
calling BenchStudio a general-purpose Transformers-level library, add and
qualify model-native task adapters, environment and checkpoint setup, and
additional task pipelines. Do not present those as available based on the
current external-process bridges alone.
