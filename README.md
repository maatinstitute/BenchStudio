# BenchStudio

BenchStudio is a proprietary evaluation layer for measuring whether embodied-AI
results remain comparable across inference schedules, simulators, and physical
execution paths.

The first implementation provides a simulator-neutral temporal scheduler and
auditable run artifacts. Policy adapters and simulator adapters are deliberately
small so RoboChallenge or another benchmark can retain authority over scoring,
safety limits, and physical robot execution.

## Quick start

```bash
python -m pytest
python -m benchstudio.cli --episodes 3 --output runs/smoke
```

Each run emits `manifest.json`, `episodes.jsonl`, and `summary.json`.

The reusable evidence layer also provides digest-tracked NDJSON artifacts and
cross-backend comparison reports for simulator-to-simulator or sim-to-real
analysis.

## Scope

The current release includes mock adapters for deterministic development. The
next adapter should target one approved simulator task and one existing policy
interface. Hardware control, emergency stops, benchmark scoring, and AGPL
`urdf-os` code remain outside this repository.

See [docs/architecture.md](docs/architecture.md) for the integration boundary.
