# Async evaluation of models, agents and robotics adapters

The public interface uses Python objects:

```python
import benchstudio as bs
from benchstudio.async_execution import AgentGroup, ResourcePool

evaluator = bs.pipeline(system=my_system, benchmark=my_benchmark,
    config=bs.EvaluationConfig(concurrency=4, timeout=30))
results = await evaluator.arun()
```

`my_system` is a `bs.System` wrapping a callable. It can wrap a model, a
complete agent workflow, or a robotics adapter's whole episode. `my_benchmark`
is a `bs.Benchmark` with separate input cases, targets and scorer. Both runtime
and scorer may be async. Construction performs no execution. Results preserve
input order regardless of completion order. The runtime owns session creation,
reset, tool permissions and cleanup; use independent sessions per trial before
increasing concurrency. Input objects are passed by reference and must not be
mutated across concurrent trials. Reusing a callable does not isolate its state.

Bounded workers limit outstanding trial tasks. A runtime or scoring exception
cancels and drains sibling workers, then propagates. No partial SystemRun is
returned on failure; persistence and resumption remain future work. Timeouts
apply to each trial, including scoring, and raise rather than scoring a timeout
as task failure. Cancellation is cooperative: blocking Python, GPU kernels and
remote work need adapter-specific termination. Sync callables run on the event
loop; use native async adapters for overlap. No threads or processes are started.

## Groups and shared resources

```python
pool = ResourcePool({"model-server": 1})
group = AgentGroup(
    {"planner": planner_system, "critic": critic_system},
    reducer=lambda outputs: outputs["planner"],
    concurrency=2, pool=pool,
    resources={"planner": ("model-server",), "critic": ("model-server",)},
)
system = bs.System.from_callable(group, name="planner-with-critic", revision="r1")
```

This primitive broadcasts the input to named members and aggregates their
outputs in declaration order. It supports async reducers and cancels siblings
when a member fails. It does not yet implement iterative communication,
arbitrary graph execution, distributed scheduling or automatic batching.
Supply a full SystemSpec for accurate component identities; from_callable
records only the declared whole-system name and revision.

ResourcePool limits admission on one event loop. Share the pool across groups
to enforce the same named capacity. Request all resources in a single lease;
nested leases are unsupported. Capacities are concurrency slots, not VRAM
reservations or GPU quotas. No speedup has been measured.

## Agent security evaluation

Run `python examples/systems/agent_security.py` for a synthetic tool-permission
example. A benchmark for real agent pentesting must pin its attack cases, threat
model, permitted tools/network, starting state, budget and independent success
criterion in its versioned definition. Distinguish attack success, defense
success and runtime failure explicitly. Test benign controls as well as attacks;
a defender that blocks everything should not appear generally capable.

BenchStudio does not sandbox arbitrary agent code. Provide an isolated tool
backend or external worker with the intended permissions before running real
attacks. The example executes neither tools nor model inference and establishes
no real security result. Evaluator authority remains false by default.

For live pi0.5, the async callable must wrap a qualified runtime adapter with
per-trial reset, server request identity, cancellation and action semantics.
This scheduler does not establish parity or qualify Protocol E or the compiled
counter. No simulator, GPU or model execution was performed for this change.
