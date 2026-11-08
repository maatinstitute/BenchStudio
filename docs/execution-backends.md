# One engine, persistent workers, independent cases

BenchStudio keeps `EvaluationEngine` as the common coordinator. It accepts either
the existing `System + Benchmark` callable interface or an installed backend for
interactive/native workloads. A session is not a public unit of execution. The
engine dispatches case requests; adapters decide which resources persist and which
state must be fresh.

```python
import benchstudio as bs

config = bs.EvaluationConfig(
    run_id="driving", output_dir="runs/driving", timeout=900, max_retries=0,
)
evaluation = bs.pipeline(
    "alpasim", model="route_following", alpasim_root="/opt/alpasim",
    scene_ids=("YOUR_INSTALLED_SCENE_ID",), config=config,
)
print(evaluation.check().summary())
results = evaluation()  # explicit native execution
print(results.summary())
```

The existing engine owns ordered dispatch, explicit incomplete-execution retries,
stop/continuation, output reservation, attempt receipts and worker shutdown.
AlpaBridge supplies per-scene execution, Docker cleanup, native artifact reports
and domain scoring. Its BenchStudio route does not invoke a separate batch loop.
The standalone public subprocess executor remains independent of private
BenchStudio for compatibility.

## For integration authors only

The ordinary researcher API is `import benchstudio as bs`, `bs.pipeline(...)`,
`evaluation.check()` and `evaluation()`. `.run()` remains supported. No backend
contract or per-case method needs to be imported or called in the researcher flow.
`CaseResult` and `ExecutionBackend` live in the separate `benchstudio.backends`
extension namespace, not the top-level `bs` namespace.

### Backend contract

| Member | Responsibility |
| --- | --- |
| `cases` | Ordered unique case IDs; backend owns payloads and scientific identity |
| `check(config)` | Static issues, without model loading or native work |
| `start(config)` | Initialize reusable worker resources and native reports once |
| `execute_case(case, attempt=..., config=...)` | Execute one request, isolate case state and clean up request resources |
| `record(case, result, attempt=...)` | Retain native accounting after each attempt, including exceptions |
| `close()` | Release reusable resources, including after partial startup or failure |
| `finish()` | Return retained native results after shutdown; do not rerun cases |

`execute_case` returns `benchstudio.backends.CaseResult(completed, output)`. Completion is operational,
not task success: a valid unsuccessful policy or agent response is complete. Raw
outputs, scores and metrics remain backend-owned. There is no universal
reset/step/reward interface or forced Boolean scientific score.

A model server or loaded weights can persist across requests. A simulator can be
new for each case, and an agent conversation can be isolated while its underlying
model remains loaded. Reset/reuse policy belongs to the adapter and benchmark;
BenchStudio does not infer independence or qualification from method names.
Existing callable-system state ownership is unchanged.

Use `bs.EvaluationEngine(backend=adapter, config=config)` or
`bs.pipeline("evaluate", backend=adapter, config=config)` for a custom backend.
[The agent contract tests](../tests/test_execution_backend.py) prove one worker
initialization, reuse of the same model object, isolated conversations and cleanup
through the same engine used by AlpaBridge. These are synthetic tests, not a
measured native acceleration claim.

## Failure, retry and retention

Core `max_retries` defaults to zero. Only returned incomplete operational results
are retryable, subject to the benchmark's explicit policy. `continue_on_error`
defaults false and applies after the retry budget is exhausted. Exceptions,
timeouts and interruptions are recorded and propagated without retrying. `close()`
always runs, even after partial startup. If cleanup also fails, the original
execution error remains primary. Task failure never automatically triggers retry.

When configured, the engine reserves a fresh output directory before startup.
`execution.json` records overall state/configuration; `cases.jsonl` records case
IDs, attempts, completion and exceptions. Raw outputs remain in the native format.
No implicit resume, cross-host lock, crash-proof consumption registry, scientific
permission or signed evidence is created. Scientific recipes retain their guards.

## Capability boundary

This backend path is sequential. Concurrent requests, model batching and async
backend execution are explicitly refused. It does not allocate GPU memory or claim
vLLM throughput. Adapters must declare and implement safe run-command timeout
support; unsupported timeouts fail check. Backend setup/teardown remains trusted
code, not subject to an enforceable whole-machine deadline.

AlpaBridge still launches a complete native process per scene; this change does
not yet establish warm-model execution there. It uses separate per-attempt output
directories and strict retained process cleanup. Native parity/performance needs
separate validation. No simulator, learned model or scientific campaign was run.

## Complete benchmark calendars

The researcher-facing route can now supply an executable `Benchmark` rather than
constructing a backend directly. Its protocol binds the configured system to this
same engine. See [benchmark protocols](benchmark-protocols.md).

Backend case IDs identify operational execution groups. They need not be individual
experimental episodes: one native program may cover many frozen BenchmarkCase
units. Engine receipts bind each execution to its planned unit IDs, while the
native result owns actual coverage and missingness. Completing a job does not
fabricate complete scientific outcomes. Protocol retry policy is captured with
its calendar and defaults to disallowing generic automatic retries.
