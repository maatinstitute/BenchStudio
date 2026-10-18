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

Install an optional Genesis backend only in the environment that owns its
runtime:

```bash
python -m pip install 'benchstudio[genesis]'
```

The Genesis adapter requires explicit scene, action, and observation callbacks;
BenchStudio does not infer task controllers or claim Genesis scoring authority.

Verify an existing run artifact offline, optionally against a digest held by
an independent reviewer or CI system:

```bash
python -m benchstudio.cli --verify-artifact runs/smoke \
  --trusted-manifest-sha256 <manifest-sha256>
```

Signed manifests can be verified with `--manifest-signature` and
`--trusted-public-key` instead of, or in addition to, the digest reference.

Audit a completed frozen campaign directory without constructing or rerunning
its model and simulator adapters:

```bash
python -m benchstudio.cli --audit-output runs/campaign
```

Use `--claim-type paired_comparison` or `--claim-type real_world_transfer` to
apply the corresponding stricter claim prerequisites during the audit.

The end-to-end frozen-campaign CI gate can be run directly with:

```bash
python -m pytest -q tests/test_ci_smoke.py
```

Compile a declarative campaign before execution (the CLI input is JSON):

```bash
python -m benchstudio.cli --campaign-spec campaign.json --plan-output campaign-plan.json
```

Each run emits `manifest.json`, `episodes.jsonl`, and `summary.json`.

Matched instrumented-versus-baseline timing can be persisted as
`execution-overhead.json` with `write_execution_overhead()`. Campaign audits
load that artifact, retain clock/boundary uncertainty, and expose deadline
misses through the `execution_overhead_valid` audit field.

Use `audit_evaluation_acceptance()` to produce the proposal’s explicit
scientific-contract gate report. It fails closed when parity, recovery,
reproducibility, statistical, or timing evidence has not been supplied.

The same gate can be run against an existing campaign directory:

```bash
python -m benchstudio.cli --audit-output runs/campaign \
  --acceptance-output runs/campaign/acceptance.json \
  --acceptance-evidence acceptance-evidence.json
```

Parity, recovery, statistics, and reproducibility reports can also be supplied
directly with `--policy-parity-report`, `--recovery-report`,
`--statistics-report`, and `--reproducibility-report`; their schemas are
interpreted conservatively and never promote missing evidence to a pass.

Compiled mock campaigns can also be audited and packaged as immutable evidence
bundles:

```bash
python -m benchstudio.cli --campaign-spec campaign.json --execute-mock \
  --audit --archive-output runs/campaign.zip
```

When a campaign declares adapter IDs, execute those frozen registry entries
directly (optional dependencies are checked before work is scheduled):

```bash
python -m benchstudio.cli --campaign-spec campaign.json --execute-registry
```

Frozen attempts can be distributed across local lease-owning workers while
retaining one append-only campaign ledger:

```bash
python -m benchstudio.cli --campaign-spec campaign.json --execute-mock --workers 4
```

The same command can publish the deterministic bundle to a local
content-addressed artifact store:

```bash
python -m benchstudio.cli --campaign-spec campaign.json --execute-mock \
  --artifact-store runs/artifacts
```

The same `ArtifactStore` contract also supports vendor-neutral HTTP PUT
publication through `HttpArtifactStore`, using the archive SHA-256 as the
immutable object path and treating an existing object as idempotent.

The CLI selects that publisher with `--artifact-url URL`; `--artifact-store`
and `--artifact-url` are mutually exclusive.

When comparing frozen simulation and physical campaign directories, add
`--transfer-backends SIMULATION=PHYSICAL` to include paired transfer-fidelity
statistics in the comparison report. Missing physical outcomes remain missing.

Model runtimes can also be kept outside BenchStudio behind the registered
`external_command` adapter. It sends one JSON request per inference and
requires a JSON response containing an `actions` array, preserving the model
runtime's ownership while retaining BenchStudio timing and evidence capture.

For loaded checkpoints and accelerator-backed policies, use the registered
`persistent_external_command` adapter. It keeps one JSON-line process alive for
`reset`, `predict`, and `close`, so process startup is not counted as inference
latency and the runtime can retain its model state between requests.

The same boundary is available under the named `smolvla` and `opendm` model
adapters. These names identify the declared VLA protocol and capability profile;
checkpoint loading, preprocessing, and accelerator ownership remain in the
external process, so no model weights are downloaded implicitly.

External simulators can use the simulator registry's `external_command`
adapter as a persistent JSON-line process. It supports `reset`, `observe`,
`step`, and `close` messages while leaving physics and safety authority in
the external runtime.

The reusable evidence layer also provides digest-tracked NDJSON artifacts and
cross-backend comparison reports for simulator-to-simulator or sim-to-real
analysis.

Matched transfer records can be analyzed and serialized directly:

```bash
python -m benchstudio.cli --transfer-records transfer.jsonl \
  --transfer-output transfer-report.json
```

Missing outcomes remain explicit and cause a non-zero validation status.

Counterfactual branch records can be summarized similarly:

```bash
python -m benchstudio.cli --recovery-records counterfactual-results.jsonl \
  --recovery-output recovery-report.json
```

Pass `--recovery-plan counterfactual-plan.json` to validate every recorded
branch against the frozen nominal/intervention plan; mismatched or missing
lineage fails closed.

Serialized counterexample discovery and confirmation plans can be checked
independently before use:

```bash
python -m benchstudio.cli --validate-search-plan search-plan.json
python -m benchstudio.cli --validate-confirmation-plan confirmation-plan.json
```

Recorded policy traces can be used as a fail-closed parity reference. The
`benchstudio.integrations.TracePolicy` adapter binds each action to its expected
observation digest, so altered preprocessing or state cannot silently reuse the
recorded action sequence. `write_parity_report()` persists the policy and
observation parity decisions as versioned JSON evidence.

The registry also exposes this boundary as the `trace` model adapter, allowing a
frozen campaign to execute a digest-bound reference trace through the normal
campaign ledger and simulator path.

Compare two or more completed or partially completed frozen campaigns directly
from their evidence directories. Missing attempts stay missing, and malformed
attempt summaries are reported as execution failures:

```bash
python -m benchstudio.cli \
  --compare-campaign sim=runs/sim \
  --compare-campaign real=runs/real \
  --comparison-scenario-id arrange_fruits \
  --comparison-output comparison.json
```

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
