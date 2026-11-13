# BenchStudio

BenchStudio is a source-available evaluation library for testing whether
embodied-AI results remain comparable across inference schedules, simulators,
and physical execution paths.

The first implementation provides a simulator-neutral temporal scheduler and
auditable run artifacts. Policy adapters and simulator adapters are deliberately
small so RoboChallenge or another benchmark can retain authority over scoring,
safety limits, and physical robot execution.

## Research examples

The [refinement-versus-refresh SmolVLA case study](examples/refinement_refresh/)
shows how retained outcomes from a published study map to BenchStudio's paired
analysis while preserving the boundary between historical evidence and new
BenchStudio-produced runs.

[**Outcome Recovery**](examples/outcome_recovery/README.md) shows how to
specify matched nominal/intervention continuations with the existing
BenchStudio campaign APIs. It can freeze a study without a simulator and
accepts a caller-owned native evaluator for actual outcomes. It is a research
application, **not** a separate execution framework or proof of recovery
improvement. See [research application ownership](docs/research-applications.md).

## Quick start

For a reproducible contributor environment, use the committed `uv.lock`:

```bash
uv sync --locked --extra dev
uv run --locked ruff check .
uv run --locked python -m pytest
```

`uv sync --locked --extra dev` installs BenchStudio editably with the locked
contributor dependencies.

### Author a paired study

The Python authoring helpers reduce condition-matrix boilerplate while still
compiling through BenchStudio's strict campaign validator:

```python
from pathlib import Path

from benchstudio import PairedStudy, condition_grid, simulator_environment

study = PairedStudy(
    name="refinement-refresh",
    task_id="held-out-task",
    conditions=condition_grid(
        generation_effort=[2, 5],
        actions_before_refresh=[2, 5],
    ),
    seeds=(11, 12, 13),
    environments=(simulator_environment("native-simulator"),),
)

plan = study.freeze()
plan.write(Path("frozen-plan.json"))
```

The helpers do not execute a policy, infer scoring semantics, or authorize a
physical robot. The resulting plan uses the same identities, protocol envelope,
validation, and digest as a hand-written campaign specification.

The authoring and frozen-plan core is checked on Linux, macOS, and Windows.
Simulator adapters and external-process integrations retain their own platform
requirements and must be qualified in the environment that executes them.

## Run and inspect a local campaign

The dependency-free mock path checks the scheduler, evidence writer, and report
pipeline without claiming simulator or model validity:

```bash
uv run --locked python -m benchstudio.cli --episodes 3 --output runs/smoke
uv run --locked python -m benchstudio.cli --audit-output runs/smoke
```

Inspect optional simulator and model-adapter availability before scheduling a
real evaluation:

```bash
uv run --locked python -m benchstudio.cli --readiness
```

## Documentation

- [Workflow and CLI reference](docs/workflows.md): campaign execution, artifact
  verification, recovery, demos, and integration fixtures.
- [Architecture](docs/architecture.md): ownership, execution, evidence, and
  adapter boundaries.
- [Resource preflight](docs/resource-preflight.md): RAM, VRAM, and optional
  runtime checks before execution.
- [Visual VLA transport](docs/visual-vla-transport.md): local image transport and
  the external SmolVLA boundary.
- [Research applications](docs/research-applications.md): how worked studies use
  the shared execution and evidence APIs.
- [Source attribution](docs/source-attribution.md): upstream provenance and
  licensing boundaries.

## Scope

The current release includes mock adapters for deterministic development. The
next adapter should target one approved simulator task and one existing policy
interface. Hardware control, emergency stops, benchmark scoring, and AGPL
`urdf-os` code remain outside this repository.

See [docs/architecture.md](docs/architecture.md) for the integration boundary.
The hosted CI matrix verifies the supported Python versions, portable core,
installed distribution, authoring types, and workflow security on every change.

## Citation

If BenchStudio supports your research, cite the version you used through
GitHub's **Cite this repository** menu or [`CITATION.cff`](CITATION.cff). Also
cite the benchmark, simulator, policy, and datasets that supply the scientific
semantics of the evaluation.

```bibtex
@software{benchstudio_2026,
  author  = {Tellez Fernandez, Alba Maria},
  title   = {BenchStudio: Evidence-aware evaluation infrastructure for embodied AI},
  year    = {2026},
  version = {0.1.0},
  url     = {https://github.com/maatinstitute/BenchStudio}
}
```

BenchStudio includes utilities for reproducing the joint generation-effort and
execution-prefix evaluation used in the companion paper, while keeping model
and simulator outcome authority external. See the
[worked example, paper, and paired outcomes](examples/refinement_refresh/).
