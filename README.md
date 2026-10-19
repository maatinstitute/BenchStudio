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

Verify a retained source snapshot against a local source checkout:

```bash
python scripts/verify_source_snapshot.py \
  docs/source-snapshots/alpabridge-27c96e6.json \
  /path/to/AlpaBridge
```

The command checks every listed file digest and rejects missing, changed, or
path-escaping entries. It does not require the historical upstream commit to
remain reachable.

Audit canonical RoboChallenge observe-only records without interpreting their
opaque payloads or claiming task success:

```bash
python -m benchstudio.cli --robochallenge-records robochallenge.jsonl \
  --robochallenge-output robochallenge-audit.json
```

The report preserves canonical base64 payloads and SHA-256 identities,
retains malformed-record failures, and explicitly marks execution and official
scoring as external.

For a transport-only local mock, send JSONL requests to
`examples/external_runtime/robochallenge_mock.py`; it emits the same canonical
records without simulating physics or scoring.

Run the checked-in observe/acknowledge/audit transport checkpoint with:

```bash
PYTHONPATH=src python examples/run_robochallenge_mock.py
```

This validates subprocess transport and payload identity only; execution and
official scoring remain external.

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

Run the complete local CI-equivalent gate, including the full suite and
cross-version-friendly bytecode compilation, with:

```bash
bash scripts/verify_local_ci.sh
```

Compile a declarative campaign before execution (the CLI input is JSON):

```bash
python -m benchstudio.cli --campaign-spec campaign.json --plan-output campaign-plan.json
```

An end-to-end frozen campaign example, including nested WorldEpisode identity
binding, is provided at
`examples/campaigns/mock-worldepisode.json`:

```bash
python -m benchstudio.cli \
  --campaign-spec examples/campaigns/mock-worldepisode.json \
  --execute-mock --workers 2 --audit \
  --output runs/mock-worldepisode
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

Scenario archives can be independently verified before extraction or campaign
scheduling:

```bash
python -m benchstudio.cli --verify-scenario-archive scenario.zip \
  --trusted-scenario-archive-sha256 <archive-sha256>
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

Published bundles can be fetched through the Python API with
`retrieve_campaign_archive()`. Retrieval verifies the content digest and
archive structure before extraction.

The same flow is available from the CLI:

```bash
python -m benchstudio.cli --fetch-artifact SHA256 \
  --artifact-store runs/artifacts --extract-output runs/retrieved-campaign
```

When comparing frozen simulation and physical campaign directories, add
`--transfer-backends SIMULATION=PHYSICAL` to include paired transfer-fidelity
statistics in the comparison report. Missing physical outcomes remain missing.
The comparison also verifies that the frozen task, model, execution semantics,
conditions, seeds, and initial-state identities match; backend declarations may
differ because that is the transfer being measured.

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

The process-backed registry path is runnable without a model package or
simulator installation:

```bash
python -m benchstudio.cli \
  --campaign-spec examples/campaigns/external-process.json \
  --execute-registry --workers 2 --audit \
  --output runs/external-process
```

The example programs under `examples/external_runtime/` are deliberately small
protocol fixtures; they do not represent model quality or physics fidelity.

For a real SmolVLA checkpoint, run
`examples/external_runtime/lerobot_smolvla_policy.py` from the separate
LeRobot environment that owns the checkpoint. Set
`BENCHSTUDIO_LEROBOT_CHECKPOINT` to a local checkpoint directory,
`BENCHSTUDIO_LEROBOT_CHECKPOINT_SHA256` to its reviewed lowercase SHA-256
identity, and provide a frozen `observation.payload.policy_batch` mapping.
Only the digest is returned in action metadata; the private checkpoint path is
not copied into BenchStudio evidence. BenchStudio does not install LeRobot,
download weights, or infer image preprocessing; those choices remain owned by
the external runtime and must be frozen in the campaign protocol.

An archived external SmolVLA/LIBERO deployment pilot can be checked without
loading its weights or runtime:

```bash
python -m benchstudio.cli \
  --smolvla-manifest /path/to/real_smolvla/manifest.json \
  --smolvla-summary /path/to/real_smolvla/results/summary.json \
  --smolvla-output smolvla-evidence.json
```

This verifies pinned checkpoint/runtime revisions and summary arithmetic while
preserving the archive's pairing and timing limitations.
Pass `--smolvla-manifest-sha256` and `--smolvla-summary-sha256` to require
independent trusted digests for both input files.

The approved physical-boundary example is
`examples/campaigns/approved-physical-boundary.json`. It includes a disabled
physical environment with explicit authorization and no-retry declarations;
compilation schedules only the enabled simulator until a separate approved
protocol enables hardware.

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

Run the checked-in matched-backend transfer fixture with:

```bash
PYTHONPATH=src python examples/run_mock_transfer.py --output runs/mock-transfer
```

It exercises frozen-plan compatibility, paired campaign loading, and transfer
gap analysis. Both backends are fixtures; execution, physics, and scoring are
external.

Exercise resumable frozen-plan recovery with:

```bash
PYTHONPATH=src python examples/run_mock_recovery.py --output runs/mock-recovery
```

The checkpoint runs a partial batch, resumes the same plan, and reports
committed, skipped, missing, and independently audited attempts.

Missing outcomes remain explicit and cause a non-zero validation status.

Counterfactual branch records can be summarized similarly:

```bash
python -m benchstudio.cli --recovery-records counterfactual-results.jsonl \
  --recovery-output recovery-report.json
```

Pass `--recovery-plan counterfactual-plan.json` to validate every recorded
branch against the frozen nominal/intervention plan; mismatched or missing
lineage fails closed.

Counterfactual plans can be compiled directly from an independently loaded
frozen campaign plan:

```bash
python -m benchstudio.cli \
  --frozen-plan campaign-plan.json \
  --counterfactual-interventions interventions.json \
  --counterfactual-output counterfactual-plan.json
```

Serialized counterexample discovery and confirmation plans can be checked
independently before use:

```bash
python -m benchstudio.cli --validate-search-plan search-plan.json
python -m benchstudio.cli --validate-confirmation-plan confirmation-plan.json
```

Result artifacts can be audited independently against those frozen plans. The
commands fail closed when rows are missing, duplicated, mis-bound, or carry
invalid outcome/failure evidence:

The checked-in mock checkpoint can be run end to end with paired nominal and
intervention branches:

```bash
python examples/run_mock_robustness.py --output runs/mock-robustness
```

It is evidence/protocol coverage only; the evaluator explicitly has no physics
or official scoring authority.

```bash
python -m benchstudio.cli \
  --search-results search-results.jsonl \
  --search-plan search-plan.json
python -m benchstudio.cli \
  --confirmation-results confirmation-results.jsonl \
  --confirmation-plan confirmation-plan.json
```

Recorded policy traces can be used as a fail-closed parity reference. The
`benchstudio.integrations.TracePolicy` adapter binds each action to its expected
observation digest, so altered preprocessing or state cannot silently reuse the
recorded action sequence. `write_parity_report()` persists the policy and
observation parity decisions as versioned JSON evidence.

The registry also exposes this boundary as the `trace` model adapter, allowing a
frozen campaign to execute a digest-bound reference trace through the normal
campaign ledger and simulator path.

The repository includes a complete local reference campaign. Replace the
placeholder digest in `examples/campaigns/trace-policy.json` with the SHA-256
of `examples/traces/mock-reference-policy.jsonl`, then run it from the
repository root:

```bash
sha256sum examples/traces/mock-reference-policy.jsonl
python -m benchstudio.cli \
  --campaign-spec examples/campaigns/trace-policy.json \
  --plan-output /tmp/benchstudio-trace-plan.json \
  --output /tmp/benchstudio-trace-campaign \
  --execute-registry --audit
```

This is a deterministic adapter and simulator checkpoint for exercising the
campaign/evidence path; it is not a claim about a downloaded model checkpoint
or benchmark performance.

For the Refinement/Refresh research campaign, BenchStudio can import the
upstream frozen plan directly instead of regenerating its schedule:

```bash
python -m benchstudio.cli \
  --refinement-plan /path/to/pilot_evaluation.json \
  --refinement-run-id smolvla-pilot \
  --plan-output /tmp/smolvla-pilot-benchstudio-plan.json
```

The importer verifies the upstream `robopad.proposed_evaluation_plan` schema,
the canonical schedule digest, contiguous identities, and duplicate planned
runs. The resulting plan records the source file digest and retains every
source schedule row for independent audit.

The imported plan can also pass through the standard resumable executor with
deterministic adapters for a protocol checkpoint:

```bash
python -m benchstudio.cli \
  --refinement-plan /path/to/pilot_evaluation.json \
  --refinement-run-id smolvla-pilot \
  --plan-output /tmp/smolvla-pilot-benchstudio-plan.json \
  --execute-mock --workers 4 --output /tmp/smolvla-pilot-campaign --audit
```

This exercises plan binding, attempt ledgers, artifact verification, and
resumable execution; it does not claim model or simulator fidelity.

RoboPAD outcome preflight artifacts can also be verified without launching
training or evaluation:

```bash
python -m benchstudio.cli --outcome-plan /path/to/smolvla-outcome-plan.json
```

This checks the `smolvla_outcome_plan_v1` payload digest, cell identities,
reserved continuation counts, and policy-query denominators. It does not turn a
preflight plan into evidence of completed model or simulator execution.

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

An existing frozen plan can also be loaded directly for recovery or execution,
without recompiling the source specification:

```bash
python -m benchstudio.cli --frozen-plan campaign-plan.json \
  --execute-mock --output runs/recovered --audit
```

## Scope

The current release includes mock adapters for deterministic development. The
next adapter should target one approved simulator task and one existing policy
interface. Hardware control, emergency stops, benchmark scoring, and AGPL
`urdf-os` code remain outside this repository.

See [docs/architecture.md](docs/architecture.md) for the integration boundary.
See [docs/implementation-audit.md](docs/implementation-audit.md) for the
verified current state and the external integrations that remain intentionally
unclaimed.
