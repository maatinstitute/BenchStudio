# BenchStudio

Evaluate AI components and interactive systems with explicit benchmarks,
retained evidence and controlled experimental identities.

**0.1.0rc2 research preview — not publicly released.** Native robotics integrations
remain experimental; see the [support matrix](docs/research-preview.md).

## Start with an existing Python system

From an authorized checkout, install into your chosen Python environment:

```sh
python -m pip install .
```

```python
import benchstudio as bs

system = bs.System.from_callable(lambda x: 2*x, name="double", revision="r1")
benchmark = bs.Benchmark(
    "arithmetic", "r1", inputs=[1, 2], targets=[2, 4],
    scorer=lambda output, target: bs.Score(success=output == target),
    evaluator_revision="exact-r1",
)
evaluation = bs.pipeline(system=system, benchmark=benchmark,
    config=bs.EvaluationConfig(output_dir="runs/first"))
print(evaluation.check().summary())
print(evaluation.capabilities)
native_results = evaluation()
report = evaluation.report()
print(report.summary())
retained = bs.inspect_result(bs.open_run("runs/first"))
```

Use a fresh output directory. This example executes arithmetic and does not
qualify a model or simulator. Configure model clients, checkpoints and generation
settings through their native APIs; supply the configured callable to System.

## Interactive systems

An installed executable Benchmark owns its task/state/seed calendar, environment
loop and scoring. Pass the configured native system and that benchmark to the
same `bs.pipeline`. One execution job can contain many experimental episodes.
Common episode evidence retains proposed/applied actions, explicit isolation
strategy, independent goal/constraint verdicts and missing identities.
No hidden environment, reset, checkpoint download or inference default is chosen.

## API and support

[Research preview guide](docs/research-preview.md) documents the 15-name supported
root API, common result inspection, capability matrix and verified integration
boundaries. Import infrastructure and optional integrations from their owning
modules; package-root wildcard exports and dynamic integration re-exports are not
provided. The only installed command is `benchstudio`; use `campaign` and `replay`
for specialist workflows. See `benchstudio --help`.

[Specialist workflows](docs/specialist-workflows.md) document task-specific
recipes and their runtime requirements. Documentation does not establish native
qualification.

## Contributing and licensing

Read [LICENSE](LICENSE) and [CONTRIBUTING.md](CONTRIBUTING.md). Noncommercial local
research is permitted. Independent redistribution/rebranding and commercial use
require permission. Used modifications must be offered upstream under the stated
return deadline. Ordinary issues/PRs require no individually signed agreement.
This is source-available research software, not OSI open source.
