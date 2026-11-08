# Pinned vLLM compatibility integration

> Preferred for researcher-owned configuration: use the native vLLM objects or
> endpoint callable described in [Native systems](native-systems.md). That route
> does not mirror vLLM options or require this compatibility pin.

Install the optional backend in a vLLM-compatible environment:

```bash
pip install 'benchstudio[vllm]'
```

The extra pins upstream vllm==0.33.0. Its Python, accelerator, PyTorch and
platform requirements apply; the dependency-free BenchStudio core remains
usable separately. No dependency or checkpoint is installed automatically.

```python
import benchstudio as bs

system = bs.System.from_pretrained(
    "your-org/supported-model",
    revision=reviewed_hugging_face_commit_sha,
    backend="vllm",
    generation=bs.GenerationConfig(max_tokens=128, temperature=0.0, seed=7),
    tensor_parallel_size=1,
)
benchmark = bs.Benchmark(
    "my-task", "dataset-r1", inputs=prompts, targets=answers,
    scorer=my_scorer, evaluator_revision="scorer-r1",
)
evaluator = bs.pipeline("system-evaluation", system=system, benchmark=benchmark)
results = evaluator(batch_size=32)
```

Configuration and construction are inert. First execution imports vLLM and
constructs upstream LLM; this can download weights and initialize accelerators.
The same engine is retained across batches and calls. Model and tokenizer use
the same full 40-character commit SHA. Remote custom code is disabled. Upstream
generation_config is set to "vllm" so model-repository defaults cannot silently
override the explicit GenerationConfig. Backend and sampling settings enter the
SystemSpec digest. Hardware/toolchain provenance and native equivalence still
need independent capture; the digest is a configuration identity.

Text prompts enter LLM.generate in batches. vLLM owns memory-aware inference
batching, kernels and caching; BenchStudio owns dataset ordering, scoring and
experimental evidence. The adapter returns one completion string per prompt and
refuses mismatched request order/count. Use a scorer returning bs.Score.
Scorer authority defaults to false until qualified. The model adapter has only
been tested with a stub engine, not live vLLM or real weights; no throughput or
numerical reproducibility claim is established.

This initial backend supports synchronous text generation only. Use run() or
the callable evaluator, with explicit batch_size. It does not implement an
async inference client, chat-template handling, multimodal preprocessing,
tool execution or automatic batching inside Workflow/AgentGroup. It serializes
engine calls and refuses invocation on an active asyncio loop before model
loading. Use the synchronous evaluation path; direct inclusion in an async
Workflow/AgentGroup needs a separate async service adapter. Native
engine teardown is owned by the producing process; no private upstream shutdown
API is invoked. Retain the vLLM process for reuse or terminate the owning process
at the job boundary. Token limits, sampling seeds and settings do not guarantee
bitwise determinism across hardware, versions or batch shapes.

Use existing from_callable systems for custom agents and native policy runtimes.
This text backend does not claim support for OpenPI pi0.5 or replace its JAX
instrumentation, controller/action semantics or qualified evaluator.

## Rust and upstream reuse

Current upstream documents VLLM_USE_RUST_FRONTEND for replacing the Python API
server frontend with vllm-rs. That is a server execution path, distinct from this
in-process LLM adapter. BenchStudio does not copy its Rust frontend or enable
that flag for offline inference. A future service adapter can consume the
upstream server interface while leaving frontend implementation to vLLM.

This adapter calls public upstream APIs; it vendors no vLLM code and adds no new
BenchStudio licensing change. vLLM and model weights retain their own licenses.

References reviewed:
- https://docs.vllm.ai/en/v0.33.0/getting_started/quickstart/
- https://docs.vllm.ai/en/latest/serving/offline_inference/
- https://docs.vllm.ai/en/stable/configuration/env_vars/
- https://github.com/vllm-project/vllm/blob/main/vllm/entrypoints/llm.py


## Audited CPU overhead

SystemSpec and benchmark protocol digests are cached because their declarations
are immutable. Records retain the same digest while avoiding repeated canonical
serialization and SHA-256 work per trial. Runtime backend/generation config
properties cannot be reassigned through the public interface after binding.

Reproduce the narrow CPU measurement with:
`python scripts/benchmark_identity_overhead.py`.
A local Python 3.12 synthetic 10-component identity test measured approximately
77 ms for 2,000 recomputations versus 0.07 ms for cached reads (five repetitions,
median). Hashes matched. These figures measure identity lookup only; they are
not a claim about inference speed, system throughput or native vLLM performance.
Rust rewrites require a representative profile demonstrating remaining CPU
bottlenecks. Inference optimizations remain delegated to upstream vLLM.
