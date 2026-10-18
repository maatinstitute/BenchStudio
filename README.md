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

Inspect optional backend and model-adapter readiness before scheduling work:

```bash
python -m benchstudio.cli --readiness
```

The end-to-end frozen-campaign CI gate can be run directly with:

```bash
python -m pytest -q tests/test_ci_smoke.py
```

Compile a declarative campaign before execution (the CLI input is JSON):

```bash
python -m benchstudio.cli --campaign-spec campaign.json --plan-output campaign-plan.json
```

Each run emits `manifest.json`, `episodes.jsonl`, and `summary.json`.

Compiled mock campaigns can also be audited and packaged as immutable evidence
bundles:

```bash
python -m benchstudio.cli --campaign-spec campaign.json --execute-mock \
  --audit --archive-output runs/campaign.zip
```

The same command can publish the deterministic bundle to a local
content-addressed artifact store:

```bash
python -m benchstudio.cli --campaign-spec campaign.json --execute-mock \
  --artifact-store runs/artifacts
```

The reusable evidence layer also provides digest-tracked NDJSON artifacts and
cross-backend comparison reports for simulator-to-simulator or sim-to-real
analysis.

The expanded foundation adds two opt-in layers:

- `benchstudio.conformance` checks observation validity, action representation,
  adapter timing capabilities, and scenario comparability at an integration
  boundary. It does not fabricate missing WorldEpisode metadata.
- `benchstudio.campaigns` freezes scenario/condition/seed/repetition matrices
  and records results in an append-only ledger keyed by `run_id`, `pair_id`,
  `condition_id`, and `attempt_id`.

These layers keep campaign methodology and evidence ownership in BenchStudio
while leaving physics engines, dataset conversion, hardware control, and
official benchmark scoring in their source repositories.

`CampaignExecutor` now makes a frozen plan authoritative: every planned
attempt is executed once, committed with its plan digest, and skipped safely on
resumption when already recorded. Existing partial attempt directories are
refused rather than silently retried. Declarative `benchstudio.campaign.v1`
maps compile into the same immutable plan format.

## Scope

The current release includes mock adapters for deterministic development. The
next adapter should target one approved simulator task and one existing policy
interface. Hardware control, emergency stops, benchmark scoring, and AGPL
`urdf-os` code remain outside this repository.

See [docs/architecture.md](docs/architecture.md) for the integration boundary.
See [docs/implementation-audit.md](docs/implementation-audit.md) for the
verified current state and the external integrations that remain intentionally
unclaimed.
