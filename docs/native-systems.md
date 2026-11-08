# Evaluate a system configured by its owner

The researcher configures the VLA policy, world model, agent system, model
backend or endpoint using that system's own API. BenchStudio binds that callable, schedules benchmark inputs,
passes its outputs to the scorer and retains evaluation evidence. It does not
choose or override temperature, seeds, caching, quantization, parallelism, chat
templates, endpoint URLs or request fields on this route.

The public flow stays `import benchstudio as bs`, `bs.pipeline(...)`, `evaluation()`.
No provider adapter, per-case executor or extra launcher script is required.

## VLA policies, world models and agents

There is no vLLM, Transformers or text-generation requirement in this path. Bind
an existing inference function that accepts your native inputs and returns your
native outputs:

```python
import benchstudio as bs

# policy was loaded/configured by its owner using its native stack.
system = bs.System.from_callable(
    policy.select_action, name="candidate-vla", revision="full-policy-controller-stack-r1",
    configuration=declared_policy_setup,
)
print(system.describe())
```

The observation object goes to that function unchanged and the native action or
action chunk reaches the benchmark's scorer unchanged. BenchStudio does not assume
string prompts, token sampling or text responses. For a world model, bind its
prediction function and score native predictions; for agents, bind the configured
workflow. No `.generate` method is required or guessed.

Direct inference on saved observations is a component evaluation, not proof of
closed-loop success. To measure complete robotic behavior, bind the configured
native rollout function, or use an installed case-execution integration that owns
the native environment and evaluator. The R22/R25 paper path keeps its existing
model-specific stacks, action semantics, qualification and permission gates; this
binding neither replaces them nor launches anything automatically.

## Native vLLM objects, with all upstream options

Install the provider version you intend to evaluate separately from the BenchStudio
core. You do not need the version-pinned compatibility extra for this route.
The following is a native-inference example; constructing LLM may load/download
weights and initialize GPUs. It is not an offline readiness command.

```python
from functools import partial
from vllm import LLM, SamplingParams
import benchstudio as bs

engine_options = dict(
    model="your-org/model", revision="FULL_REVIEWED_MODEL_COMMIT",
    tensor_parallel_size=2, gpu_memory_utilization=0.8,
    max_num_seqs=64, enable_prefix_caching=True,
)
sampling_options = dict(temperature=0.4, max_tokens=256, top_k=40, seed=7)

llm = LLM(**engine_options)
sampling = SamplingParams(**sampling_options)
system = bs.System.from_callable(
    partial(llm.generate, sampling_params=sampling, use_tqdm=False),
    name="candidate", revision="frozen-model-and-generation-settings-r1",
    batched=True,
    configuration={"engine": engine_options, "sampling": sampling_options},
    dependencies=("vllm",),
)
print(system.describe())

benchmark = bs.Benchmark(
    "my-task", "dataset-r1", inputs=prompts, targets=answers,
    scorer=lambda output, target: bs.Score(success=output.outputs[0].text == target),
    evaluator_revision="first-completion-exact-match-r1",
)
evaluation = bs.pipeline(
    system=system, benchmark=benchmark,
    config=bs.EvaluationConfig(batch_size=32, output_dir="runs/native-vllm"),
)
results = evaluation()
print(results.summary())
```

All `engine_options` and `sampling_options` go to upstream constructors, not a
BenchStudio whitelist. The actual SamplingParams object goes unchanged to
`llm.generate`. Adding an upstream option requires changing that native code,
not updating BenchStudio's parameter list. Native RequestOutput objects reach the
scorer unchanged; the example explicitly chooses the first completion. BenchStudio
does not enforce a text-only or one-completion schema inside those native objects.

Transformers works the same way: construct its pipeline using its own options,
then pass that callable to `System.from_callable(..., batched=True)`. The benchmark
scorer handles the pipeline's native result type. Models, world models and agent
systems can use any configured callable; no inference-method name is inferred.

## An endpoint selected by the researcher

This example uses an already provisioned completions-compatible service. It makes
network calls only when the evaluation is explicitly executed.

```python
import os
from openai import OpenAI
import benchstudio as bs

endpoint = "http://localhost:8000/v1"
client = OpenAI(base_url=endpoint, api_key=os.environ["INFERENCE_API_KEY"])
request_options = dict(model="operator-selected-model", temperature=0.25, max_tokens=200)

system = bs.System.from_callable(
    lambda prompt: client.completions.create(prompt=prompt, **request_options),
    name="remote-candidate", revision="frozen-deployment-and-request-r1",
    configuration={"endpoint": endpoint, "request": request_options},
    dependencies=("openai",),
)
print(system.describe())
# Use with the existing bs.pipeline(system=system, benchmark=benchmark, config=...).
# The scorer receives the native SDK response, not an inferred text field.
```

Credentials stay in the client/environment. Configuration declarations are retained
verbatim as evidence, so do not include API keys or authorization headers. The
service owner controls its deployment; BenchStudio cannot infer remote weights,
server versions or undisclosed defaults from an endpoint URL. Declare and retain
those separately when reproducibility requires them.

## Visible configuration and evidence

`configuration=` is an optional user-declared provenance mapping, not an inference
configuration schema. It is not forwarded as kwargs, interpreted as provider
settings or used to construct a client/model. The callable remains the sole source
of inference behavior. Python objects configure the provider; this declaration is
only an inspectable record. No JSON configuration file is required.

`system.describe()` shows the declared endpoint/parameters, named distribution
versions, revision and system digest without invoking inference. The declaration
is copied into the immutable SystemSpec and retained as `system.json` with the run;
changing it or a recorded distribution version changes the system identity. Selected
distribution versions come from installed-package metadata, not a hardcoded vLLM
version requirement. A new System after an upstream upgrade records the new version.
The default callable path keeps its existing identities when no new options are used.

If configuration is omitted, the description labels it `opaque`; BenchStudio does
not invent values or pretend to know native defaults. If a declared mapping is
changed after binding, check/execution refuses and asks for a new System, preventing
silent changes under the old declaration. This guards the declaration only:
mutations inside opaque native objects, closures or remote servers are not inspected
or certified. The owner must keep the effective runtime and its declaration aligned.
A system revision should identify the full frozen setup, including inference settings,
not merely a mutable model alias.

Native responses are delivered to the scorer; ordinary SystemRun retention contains
scores and declared system evidence, not an automatic dump of every native response.
Backend-native logging can retain additional outputs where appropriate. BenchStudio
remains responsible for its scheduling, accounting and scoring implementation;
user-owned inference settings do not excuse evaluation defects.

## Execution contract and compatibility

With `batched=True`, the callable accepts a list and returns one ordered output per
input. A scalar call is a one-item batch. Count mismatches and accidental string/
mapping batch responses fail before scoring. Output alignment is the callable's
contract; opaque outputs are not inspected for prompt IDs. Streaming and async batch
functions are not supported by this binding. Native scalar async callables continue
to use `await evaluation.arun()`; synchronous batch bindings reject that path.

Framework construction, downloads, worker cleanup and endpoint credentials belong
to the owner of the native object. No automatic device move, eval-mode change,
precision switch, generation default, retry or provider upgrade occurs in this
binding. An upstream change preserving the callable/result contract needs no
BenchStudio option update; breaking signatures or output semantics can still require
caller/benchmark changes. Freeze versions within a campaign and upgrade deliberately
between evaluations.

`System.from_pretrained(..., backend="vllm")`, `VLLMConfig` and `GenerationConfig`
remain available as a tested, version-pinned compatibility path. Their restricted
configuration is not the preferred route for arbitrary native options. Nothing here
qualifies a simulator, policy, checkpoint, native parity or scientific campaign.
