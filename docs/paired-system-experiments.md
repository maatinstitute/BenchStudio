# Paired component experiments with Python objects

Use an executable system as the unit under evaluation. A model, a whole agent
workflow, an AgentGroup or a robotics episode adapter can be a System. A
Workflow composes named stages in order, passing each output to the next input.
A stage can itself wrap a composed system. Stages can be sync or async;
synchronous stages must not block the event loop.

```python
import benchstudio as bs
from benchstudio.experimental import Workflow

reference = Workflow("agent-stack", "r1", stages={
    "predictor": predictor_system,
    "planner": planner_system,
    "controller": controller_system,
})
candidate = reference.replace("predictor", new_predictor_system, revision="r2")
experiment = bs.pipeline(
    "ablation", reference=reference.as_system(), candidate=candidate.as_system(),
    benchmark=benchmark, changed_components=("predictor",),
    metrics=("prediction_error",),
)
result = await experiment.arun(concurrency=1, timeout=30)
print(result.summary())
```

All configuration is Python. No JSON file is needed. Workflow creates its
declared component graph and binds each nested SystemSpec digest. replace()
returns a new workflow, preserving the other stage objects and declared wiring.
It does not clone the underlying model or runtime. The stage table and its spec
cannot be reassigned through the ordinary public interface.

Ablation construction checks for undeclared component/wiring/metadata changes
before execution. Each benchmark case runs both arms. Order alternates AB/BA by
index and is recorded in result.arm_order. This balances arm counts for even
cohorts but is not randomization and does not remove time/carryover confounding.
Result ordering follows benchmark ordering even with concurrent workers.

Both arm inputs are copied before either is invoked. Targets are independently
copied for scoring. clone_input= may provide an adapter-specific clone instead
of deepcopy. Runtimes still own reset, RNG isolation, sessions, cache handling,
permissions and cleanup. Copies cannot isolate external tools, mutable model
state, environments or globally shared randomness. The same frozen planner
object may still contain mutable runtime state; resetting that state is the
adapter's responsibility. Use concurrency>1 only with independent trial sessions.

Each arm executes through the common SystemEvaluationPipeline scoring path.
Timeouts apply per arm, including scoring, and remain cooperative. Any runtime,
copying or scoring error aborts the study; infrastructure errors are not task
failures. This version does not persist partial results or resume after failure.
Continuous-only scorers are supported. Numeric comparison requires explicit
metric selection and qualified scorer authority; authority defaults to false.
The summary labels missing binary outcomes separately from numeric deltas.

The result contains both native SystemRun objects, structural audit, comparison
and arm order. Matching and descriptive statistics reuse the existing analysis.
Graph identity is a declaration, not proof that a specific implementation ran.
Structural isolation and paired outcomes alone do not establish a causal effect,
statistical power or benchmark validity. Pin dataset/scorer revisions, qualify
native boundaries, retain the planned population and validate missingness rules
for any research claim.

Run the complete offline example with:

```bash
python examples/systems/paired_ablation.py
```

It uses exact arithmetic fixtures and a fixture scorer explicitly marked
qualified for those fixtures. It demonstrates component execution and paired
comparison, not learned world-model quality or robotics performance. For agent
pentesting a stage may wrap a tool-permission mechanism, with a separately
versioned attack/benign-control benchmark and an isolated tool runtime. For live
pi0.5, supply the qualified episode adapter. No real security campaign, model,
simulator, GPU or reserved confirmation identity is needed for this example.

Workflow currently implements ordered stages. A group can run parallel members
within a stage; iterative messaging and arbitrary feedback graphs are not yet
executed by this runtime. AlpaBridge's live native paths remain a separate
migration/qualification task.
