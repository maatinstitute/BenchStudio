# System evaluation engine

Use the existing System + Benchmark + pipeline interface. EvaluationConfig declares execution settings; the backend/model configuration remains on System and scoring/dataset identity remains on Benchmark.

```python
import benchstudio as bs

system = bs.System.from_callable(lambda x: x * 2, name="example", revision="r1")
benchmark = bs.Benchmark("arithmetic", "data-r1", [1, 2], [2, 4],
    lambda output, target: bs.Score(output == target), evaluator_revision="exact-r1")
pipe = bs.pipeline("system-evaluation", system=system, benchmark=benchmark,
                   config=bs.EvaluationConfig(run_id="comparison"))
check = pipe.check()  # static compatibility; no runtime call or weight loading
results = pipe.run()
```

SystemEvaluationPipeline is a facade of EvaluationEngine, sharing the same execution loop. Direct engine users can pass the same system, benchmark and configuration. Existing run_id/batch_size/arun arguments stay compatible; supplying run_id alongside a config is rejected rather than silently overriding it.

For a batching backend use EvaluationConfig(batch_size=8). For cooperative asynchronous systems use EvaluationConfig(concurrency=4, timeout=30) and await pipe.arun(). Unsupported async batching and synchronous concurrency/timeouts fail before system execution. Async cancellation cannot interrupt blocking Python or native kernels. Concurrent trials require independently managed runtime state.

check(mode="sync" or "async") returns configuration_valid and issues. Native validity is always explicitly unverified by this static check. It does not install dependencies, download/check checkpoints, qualify evaluators or authorize a campaign. Runtime/scorer exceptions propagate; they are never converted into task failure.

System.from_pretrained continues to use the existing optional upstream vLLM backend. Callable systems can wrap agents, world models and composed architectures. No new universal VLA/WAM loader is claimed. Legacy campaign execution/CLI still uses CampaignExecutor; this change unifies the system-evaluation path, not those distinct scientific protocols.


For installed backend resolution, dependency checks, retained results and the shared
Python/CLI workflow, see [system evaluation](system-evaluation.md).
