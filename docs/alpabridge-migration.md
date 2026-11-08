# AlpaBridge integration status

AlpaBridge now supplies an optional installed `alpasim` pipeline using the existing
`bs.pipeline` extension point. Its batch executor delegates process ownership,
stdout/stderr retention and structured receipts to BenchStudio. Scene selection,
retry limits, native launcher/readiness, container cleanup, artifact audits and
batch accounting remain in AlpaBridge. No second scene scheduler is introduced.

```python
import benchstudio as bs

evaluation = bs.pipeline(
    "alpasim", model="route_following", alpasim_root="/opt/alpasim",
    config=bs.EvaluationConfig(run_id="driving", output_dir="runs/alpasim-batch"),
    scene_ids=("YOUR_INSTALLED_SCENE_ID",),
)
print(evaluation.check().summary())
results = evaluation.run()  # explicit native execution
print(results.summary())
```

Install AlpaBridge to register the pipeline and install the reviewed BenchStudio
distribution separately. AlpaBridge's public package has no mandatory dependency
on private BenchStudio. Its original batch executor remains the default.
See [AlpaBridge integration documentation](https://github.com/amtellezfernandez/AlpaBridge/blob/main/docs/benchstudio.md)
for the matching CLI, five supported batch presets and native prerequisites.

`check()` checks configuration without launching Docker, simulators or models;
it explicitly leaves native verification pending. Synthetic tests cover retained
process logs, exit status, missing artifacts, interrupted cleanup, retry accounting,
CLI checks and pipeline discovery. They do not establish native parity or speed.
Driver transport, calibration/freshness, trajectory semantics, installed scenes,
learned model dependencies and scientific outcome scoring remain backend concerns.
This implementation does not justify retiring those AlpaBridge adapters.

## Structured process results

`ProcessCommand.run(log_dir)` remains compatible and returns a receipt path.
`ProcessCommand.execute(log_dir, check=False)` additionally returns a `ProcessResult`
with `returncode`, `receipt_path`, `stdout_path`, `stderr_path` and `duration` (seconds).
Nonzero status can therefore feed the native retry/accounting rules without parsing
error messages. Timeout and required-service loss always raise `ProcessFailure`;
its `result` retains the receipt after termination. No automatic retry is added.
Process exit status is never interpreted as scientific success by this primitive.

Installed pipeline CLI reports may omit `execution_authorized` when that concept
does not apply. An explicit `False` still blocks a check; paper recipes retain their
own explicit permission gates. A result with `successful=False` produces a nonzero
CLI exit so a partial native batch cannot be reported as a successful CLI run.

## Shared configuration and retained native results

The AlpaSim integration now consumes `EvaluationConfig` and returns the common
`EvaluationCheck`. `configuration_valid` is static only; `technical_ready` is a
compatibility alias for installed recipes. `summary()` explains pending native
verification. AlpaSim rejects unsupported batching/concurrency instead of ignoring
those options. The system and AlpaSim CLIs accept `--output-dir` and the existing
`--output` alias.

Native metrics, their coverage counts, failure taxonomy and claim boundaries are
available directly on the returned AlpaBridge result. They are computed by its
existing batch summary, not a BenchStudio substitute scoring function:

```python
print(results.metrics)
print(results.audit["failure_taxonomy"])
results = bs.open_run("runs/alpasim-batch", backend="alpasim")
print(results.summary())
```

`open_run` resolves the explicitly selected installed pipeline's `open_run` reader.
It does not create a pipeline instance or execute its `run()` method. Without a
backend it still verifies the original system-run manifest and digests. Native
readers own their native evidence checks; selecting one does not add system-run
signature or digest guarantees. AlpaBridge reconstructs its existing offline
summary and does not rewrite evidence. Full scene completion is exposed separately
from acceptance by the native sensor/route/provenance audit; neither establishes
scientific qualification or task success.
