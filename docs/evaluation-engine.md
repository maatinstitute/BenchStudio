# System evaluation engine

Use the existing System + Benchmark + pipeline interface. EvaluationConfig declares execution settings; the backend/model configuration remains on System and scoring/dataset identity remains on Benchmark.

```python
import benchstudio as bs

system = bs.System.from_callable(lambda x: x * 2, name="example", revision="r1")
benchmark = bs.Benchmark("arithmetic", "data-r1", [1, 2], [2, 4],
    lambda output, target: bs.Score(output == target), evaluator_revision="exact-r1")
pipe = bs.pipeline("evaluate", system=system, benchmark=benchmark,
                   config=bs.EvaluationConfig(run_id="comparison"))
check = pipe.check()  # static configuration check; no runtime call or weight loading
results = pipe.run()
```

`SystemEvaluationPipeline` uses the same execution loop as `EvaluationEngine`.
Pass execution settings through one `EvaluationConfig`; run and async calls do not
accept configuration overrides.

For a batching backend use EvaluationConfig(batch_size=8). For cooperative asynchronous systems use EvaluationConfig(concurrency=4, timeout=30) and await pipe.arun(). Unsupported async batching and synchronous concurrency/timeouts fail before system execution. Async cancellation cannot interrupt blocking Python or native kernels. Concurrent trials require independently managed runtime state.

check(mode="sync" or "async") returns configuration_valid and issues. Native validity is always explicitly unverified by this static check. It does not install dependencies, download/check checkpoints, qualify evaluators or authorize a campaign. Runtime/scorer exceptions propagate; they are never converted into task failure.

Callable systems can wrap agents, world models and composed architectures. BenchStudio
has no universal checkpoint loader; providers keep their native configuration and
inference APIs. Specialized robotics and campaign interfaces keep their own
scientific protocols and accounting.


For installed backend resolution, dependency checks, retained results and the shared
Python/CLI workflow, see [system evaluation](system-evaluation.md).
