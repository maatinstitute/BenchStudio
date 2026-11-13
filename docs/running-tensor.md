# RunningTensor-backed policies

[RunningTensor](https://arxiv.org/abs/2609.12814) replaces a matrix recurrent
state with an order-$o$ tensor. ReVa can evaluate a robot policy that uses this
backbone through the persistent external-process boundary. ReVa does not
implement or reproduce the architecture, and the paper does not currently link
an official public implementation or robot-policy checkpoint.

The `running_tensor` adapter freezes the state order, width, element size, and
recurrent or parallel execution form for each attempt. It also derives the
declared recurrent-state size as `width ** order * state_dtype_bytes`. The
external runtime remains responsible for loading the model, applying these
controls, returning action chunks, and reporting measured accelerator memory.

```python
from reva.model_adapters import default_model_registry

policy = default_model_registry().create(
    "running_tensor",
    command=["python", "my_running_tensor_policy.py"],
    state_order=3,
    state_width=128,
    state_dtype_bytes=2,
    recurrence_form="recurrent",
)
```

The child process receives `REVA_RECURRENT_STATE_ORDER`,
`REVA_RECURRENT_STATE_WIDTH`, `REVA_RECURRENT_STATE_DTYPE_BYTES`,
`REVA_RECURRENT_STATE_BYTES`, and `REVA_RECURRENCE_FORM`. It uses the same
line-delimited request and response protocol as ReVa's persistent external
policy adapter.

For paired studies, place architecture controls in each condition's
`model_controls`. ReVa merges them into the adapter configuration only for that
attempt, so order 2 and order 3 runs can share task seeds and simulator
conditions. Keep parameter count, training data, checkpoint selection, and
state width matched or report them as separate factors. At minimum, compare
task success, host and accelerator latency, peak memory, recurrent-state bytes,
and failure or timeout rates. A robot-policy study must validate the wrapper and
success instrumentation independently before attributing an effect to state
order.
