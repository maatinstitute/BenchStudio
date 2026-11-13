# IVal workflow reference

These commands cover optional runtimes, artifact verification, campaign
execution, recovery, and integration fixtures. Run them from a IVal
checkout after creating the locked environment described in the main README.

## Visual VLA execution on a constrained host

See [local mmap tensor transport and the pinned SmolVLA + MuJoCo runner](visual-vla-transport.md).
The optional MuJoCo camera path produces real RGB frames; a persistent LeRobot
policy can consume checkpoint-preprocessed numeric tensors through private
same-host mmap files rather than JSON pixel lists. No model, asset, GPU memory,
task-success, or normalization compatibility claim is made by these fixtures.


```bash
uv run --locked python -m pytest
uv run --locked python -m ival.cli --episodes 3 --output runs/smoke
```

Inspect optional backend and model-adapter readiness before scheduling work:

```bash
uv run --locked python -m ival.cli --readiness
```

Readiness now includes a hardware-memory snapshot. To reject estimated per-worker
RAM/VRAM overcommit before constructing model/simulator adapters, declare
`execution.resource_request` in a frozen campaign. See
[resource preflight and the real MuJoCo slider baseline](resource-preflight.md).


Install an optional Genesis backend only in the environment that owns its
runtime:

```bash
uv sync --locked --extra genesis
```

The Genesis adapter requires explicit scene, action, and observation callbacks;
IVal does not infer task controllers or claim Genesis scoring authority.

## Artifact and source verification

Verify an existing run artifact offline, optionally against a digest held by
an independent reviewer or CI system:

```bash
uv run --locked python -m ival.cli --verify-artifact runs/smoke \
  --trusted-manifest-sha256 <manifest-sha256>
```

Signed manifests can be verified with `--manifest-signature` and
`--trusted-public-key` instead of, or in addition to, the digest reference.

Verify a retained source snapshot against a local source checkout:

```bash
uv run --locked python scripts/verify_source_snapshot.py \
  docs/source-snapshots/alpabridge-27c96e6.json \
  /path/to/AlpaBridge
```

The command checks every listed file digest and rejects missing, changed, or
path-escaping entries. It does not require the historical upstream commit to
remain reachable.

## External protocol records

Audit canonical RoboChallenge observe-only records without interpreting their
opaque payloads or claiming task success:

```bash
uv run --locked python -m ival.cli --robochallenge-records robochallenge.jsonl \
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
uv run --locked python examples/run_robochallenge_mock.py
```

This validates subprocess transport and payload identity only; execution and
official scoring remain external.

## Campaign audits

Audit a completed frozen campaign directory without constructing or rerunning
its model and simulator adapters:

```bash
uv run --locked python -m ival.cli --audit-output runs/campaign
```

Use `--claim-type paired_comparison` or `--claim-type real_world_transfer` to
apply the corresponding stricter claim prerequisites during the audit.

The end-to-end frozen-campaign CI gate can be run directly with:

```bash
uv run --locked python -m pytest -q tests/test_ci_smoke.py
```

## Local demonstration

For a presentation-ready local demo, including the existing URDF Studio SO-101
robot performing a cube-lift evaluation in MuJoCo, run:

```bash
bash scripts/demo.sh /tmp/ival-demo --serve
```

It executes four seeded URDF Studio episodes through its native MuJoCo runner,
varying the cube pose inside a fixed grasp region while keeping the policy and
checker frozen. It then replays every episode's recorded SO-101 joints and cube
poses through that same backend, producing one visible 3D video per episode.
URDF Studio's portable schematic recordings are retained as
`episode-schematic.mp4`. The connector adds explicit damping to the staged
URDF copy because the upstream demonstration URDF does not declare joint
dynamics; the upstream checkout remains unchanged. The control room binds the
waypoint policy by SHA-256 and exposes its timed events for inspection.
The default demo requests both MuJoCo and Genesis with the same frozen inputs;
the simulator matrix reports evaluated, failed, or unavailable backends without
turning missing runs into zero scores. IVal adds campaign accounting,
robustness evidence, matched transfer, and the RoboChallenge transport audit,
then serves the robot episode batch and evidence in the Eval Control Room at
`http://127.0.0.1:8765`. The generated files
under `/tmp/ival-demo` remain inspectable evidence artifacts. If that
directory already exists, the script creates a timestamped sibling rather than
overwriting it. These fixtures demonstrate IVal's execution and audit
boundaries; they are not physical-robot or model-quality results. IVal
auto-detects a sibling `urdf-studio` checkout. Otherwise set
`URDF_STUDIO_ROOT=/path/to/urdf-studio`. Limit or reorder the requested backends
with `IVAL_SIMULATORS=mujoco`, `genesis`, or `mujoco,genesis`.

The included SO-101 batch is a contact-grasp diagnostic fixture. The staged URDF
keeps the upstream visual model and kinematics, retains only the exact fixed-
and moving-finger mesh collisions, and adds joint damping.
The policy is not allowed to weld or attach the cube. Multiple seeds vary cube
placement while preserving the policy, checker, and simulator parameters. A
failure is a first-class result: each episode records cube displacement and
lift, sampled contact and bilateral-retention frames, gripper target tracking,
failure timing, source hashes, and a bounded root-cause classification.

The ordinary rollout trace remains sampled at 50 Hz. IVal therefore
runs a deterministic diagnostic replay that inspects every 0.2 ms MuJoCo
physics step (5 kHz) and retains every robot-cube contact: geom pair, world
position and frame, penetration, friction, solver force and torque, cube pose
and velocity, joint positions and velocities, targets, and actuator forces.
The replay is accepted only when success, stop reason, step count, and final
cube position match the evaluated run. These are simulator solver values, not
calibrated hardware-force measurements. The fixture is useful for debugging
policy/geometry/controller mismatch, but is not a hardware-contact or
real-world-transfer benchmark.

Episode 03 also runs a linked causal intervention. Attempt 01 repeats the
baseline failure. Attempt 02 keeps the seed, cube pose, simulator, checker,
geometry, and joint targets fixed but doubles the approach duration from 1.2 s
to 2.4 s. This directly tests whether lower approach velocity reduces the
pre-close collision. The dashboard reports both outcome and tradeoff (peak
normal force and cube displacement), so lower force cannot be mistaken for
recovery when the lift still fails. Both videos, reports, traces, contact
analyses, policy hashes, and the changed parameter are retained in
`recovery.json`.

## Contributor verification

Run the complete local CI-equivalent gate, including the full suite and
cross-version-friendly bytecode compilation, with:

```bash
bash scripts/verify_local_ci.sh
```

## Campaign compilation and execution

For SLURM arrays and Kubernetes Indexed Jobs, including the shared-filesystem
contract and resume procedure, see [cluster execution](cluster-execution.md).

Compile a declarative campaign before execution (the CLI input is JSON):

```bash
uv run --locked python -m ival.cli --campaign-spec campaign.json --plan-output campaign-plan.json
```

An end-to-end frozen campaign example, including nested WorldEpisode identity
binding, is provided at
`examples/campaigns/mock-worldepisode.json`:

```bash
uv run --locked python -m ival.cli \
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
uv run --locked python -m ival.cli --audit-output runs/campaign \
  --acceptance-output runs/campaign/acceptance.json \
  --acceptance-evidence acceptance-evidence.json
```

Parity, recovery, statistics, and reproducibility reports can also be supplied
directly with `--policy-parity-report`, `--recovery-report`,
`--statistics-report`, and `--reproducibility-report`; their schemas are
interpreted conservatively and never promote missing evidence to a pass.

## Archives and artifact stores

Compiled mock campaigns can also be audited and packaged as immutable evidence
bundles:

```bash
uv run --locked python -m ival.cli --campaign-spec campaign.json --execute-mock \
  --audit --archive-output runs/campaign.zip
```

Scenario archives can be independently verified before extraction or campaign
scheduling:

```bash
uv run --locked python -m ival.cli --verify-scenario-archive scenario.zip \
  --trusted-scenario-archive-sha256 <archive-sha256>
```

When a campaign declares adapter IDs, execute those frozen registry entries
directly (optional dependencies are checked before work is scheduled):

```bash
uv run --locked python -m ival.cli --campaign-spec campaign.json --execute-registry
```

Frozen attempts can be distributed across local lease-owning workers while
retaining one append-only campaign ledger:

```bash
uv run --locked python -m ival.cli --campaign-spec campaign.json --execute-mock --workers 4
```

The same command can publish the deterministic bundle to a local
content-addressed artifact store:

```bash
uv run --locked python -m ival.cli --campaign-spec campaign.json --execute-mock \
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
uv run --locked python -m ival.cli --fetch-artifact SHA256 \
  --artifact-store runs/artifacts --extract-output runs/retrieved-campaign
```

## Cross-backend and external runtimes

When comparing frozen simulation and physical campaign directories, add
`--transfer-backends SIMULATION=PHYSICAL` to include paired transfer-fidelity
statistics in the comparison report. Missing physical outcomes remain missing.
The comparison also verifies that the frozen task, model, execution semantics,
conditions, seeds, and initial-state identities match; backend declarations may
differ because that is the transfer being measured.

Model runtimes can also be kept outside IVal behind the registered
`external_command` adapter. It sends one JSON request per inference and
requires a JSON response containing an `actions` array, preserving the model
runtime's ownership while retaining IVal timing and evidence capture.

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
uv run --locked python -m ival.cli \
  --campaign-spec examples/campaigns/external-process.json \
  --execute-registry --workers 2 --audit \
  --output runs/external-process
```

The example programs under `examples/external_runtime/` are deliberately small
protocol fixtures; they do not represent model quality or physics fidelity.

For a real SmolVLA checkpoint, run
`examples/external_runtime/lerobot_smolvla_policy.py` from the separate
LeRobot environment that owns the checkpoint. Set
`IVAL_LEROBOT_CHECKPOINT` to a local checkpoint directory,
`IVAL_LEROBOT_CHECKPOINT_SHA256` to its reviewed lowercase SHA-256
identity, and provide a frozen `observation.payload.policy_batch` mapping.
Only the digest is returned in action metadata; the private checkpoint path is
not copied into IVal evidence. IVal does not install LeRobot,
download weights, or infer image preprocessing; those choices remain owned by
the external runtime and must be frozen in the campaign protocol.

An archived external SmolVLA/LIBERO deployment pilot can be checked without
loading its weights or runtime:

```bash
uv run --locked python -m ival.cli \
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

## Transfer, recovery, and counterfactual workflows

The reusable evidence layer also provides digest-tracked NDJSON artifacts and
cross-backend comparison reports for simulator-to-simulator or sim-to-real
analysis.

Matched transfer records can be analyzed and serialized directly:

```bash
uv run --locked python -m ival.cli --transfer-records transfer.jsonl \
  --transfer-output transfer-report.json
```

Run the checked-in matched-backend transfer fixture with:

```bash
uv run --locked python examples/run_mock_transfer.py --output runs/mock-transfer
```

It exercises frozen-plan compatibility, paired campaign loading, and transfer
gap analysis. Both backends are fixtures; execution, physics, and scoring are
external.

Exercise resumable frozen-plan recovery with:

```bash
uv run --locked python examples/run_mock_recovery.py --output runs/mock-recovery
```

The checkpoint runs a partial batch, resumes the same plan, and reports
committed, skipped, missing, and independently audited attempts.

Exercise parallel lease-owning workers with:

```bash
uv run --locked python examples/run_mock_workers.py --output runs/mock-workers --workers 3
```

This verifies shared lease ownership and exactly-once ledger accounting for a
local fixture campaign.

Missing outcomes remain explicit and cause a non-zero validation status.

Counterfactual branch records can be summarized similarly:

```bash
uv run --locked python -m ival.cli --recovery-records counterfactual-results.jsonl \
  --recovery-output recovery-report.json
```

Pass `--recovery-plan counterfactual-plan.json` to validate every recorded
branch against the frozen nominal/intervention plan; mismatched or missing
lineage fails closed.

Counterfactual plans can be compiled directly from an independently loaded
frozen campaign plan:

```bash
uv run --locked python -m ival.cli \
  --frozen-plan campaign-plan.json \
  --counterfactual-interventions interventions.json \
  --counterfactual-output counterfactual-plan.json
```

Serialized counterexample discovery and confirmation plans can be checked
independently before use:

```bash
uv run --locked python -m ival.cli --validate-search-plan search-plan.json
uv run --locked python -m ival.cli --validate-confirmation-plan confirmation-plan.json
```

Result artifacts can be audited independently against those frozen plans. The
commands fail closed when rows are missing, duplicated, mis-bound, or carry
invalid outcome/failure evidence:

The checked-in mock checkpoint can be run end to end with paired nominal and
intervention branches:

```bash
uv run --locked python examples/run_mock_robustness.py --output runs/mock-robustness
```

It is evidence/protocol coverage only; the evaluator explicitly has no physics
or official scoring authority.

```bash
uv run --locked python -m ival.cli \
  --search-results search-results.jsonl \
  --search-plan search-plan.json
uv run --locked python -m ival.cli \
  --confirmation-results confirmation-results.jsonl \
  --confirmation-plan confirmation-plan.json
```

## Trace parity

Recorded policy traces can be used as a fail-closed parity reference. The
`ival.integrations.TracePolicy` adapter binds each action to its expected
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
uv run --locked python -m ival.cli \
  --campaign-spec examples/campaigns/trace-policy.json \
  --plan-output /tmp/ival-trace-plan.json \
  --output /tmp/ival-trace-campaign \
  --execute-registry --audit
```

This is a deterministic adapter and simulator checkpoint for exercising the
campaign/evidence path; it is not a claim about a downloaded model checkpoint
or benchmark performance.

## Refinement and refresh study imports

For the Refinement/Refresh research campaign, IVal can import the
upstream frozen plan directly instead of regenerating its schedule:

```bash
uv run --locked python -m ival.cli \
  --refinement-plan /path/to/pilot_evaluation.json \
  --refinement-run-id smolvla-pilot \
  --plan-output /tmp/smolvla-pilot-ival-plan.json
```

The importer verifies the upstream `robopad.proposed_evaluation_plan` schema,
the canonical schedule digest, contiguous identities, and duplicate planned
runs. The resulting plan records the source file digest and retains every
source schedule row for independent audit.

Callers with a separately frozen runtime envelope can pass it as
`execution_protocol={"M": ..., "S": ..., "P": ...}` to
`compile_refinement_source_plan()`. The envelope becomes part of the plan
digest and can then be executed through the ordinary model/simulator registries.
The CLI equivalent is `--refinement-execution-protocol protocol.json`; combine
it with `--execute-registry` only when the external adapters and their runtime
dependencies are available.

The imported plan can also pass through the standard resumable executor with
deterministic adapters for a protocol checkpoint:

```bash
uv run --locked python -m ival.cli \
  --refinement-plan /path/to/pilot_evaluation.json \
  --refinement-run-id smolvla-pilot \
  --plan-output /tmp/smolvla-pilot-ival-plan.json \
  --execute-mock --workers 4 --output /tmp/smolvla-pilot-campaign --audit
```

This exercises plan binding, attempt ledgers, artifact verification, and
resumable execution; it does not claim model or simulator fidelity.

Legacy outcome preflight artifacts can also be verified without launching
training or evaluation:

```bash
uv run --locked python -m ival.cli --outcome-plan /path/to/smolvla-outcome-plan.json
```

This checks the `smolvla_outcome_plan_v1` payload digest, cell identities,
reserved continuation counts, and policy-query denominators. It does not turn a
preflight plan into evidence of completed model or simulator execution.

## Campaign comparison and recovery

Compare two or more completed or partially completed frozen campaigns directly
from their evidence directories. Missing attempts stay missing, and malformed
attempt summaries are reported as execution failures:

```bash
uv run --locked python -m ival.cli \
  --compare-campaign sim=runs/sim \
  --compare-campaign real=runs/real \
  --comparison-scenario-id arrange_fruits \
  --comparison-output comparison.json
```

The expanded foundation adds two opt-in layers:

- `ival.conformance` checks observation validity, action representation,
  adapter timing capabilities, and scenario comparability at an integration
  boundary. It does not fabricate missing WorldEpisode metadata.
- `ival.campaigns` freezes scenario/condition/seed/repetition matrices
  and records results in an append-only ledger keyed by `run_id`, `pair_id`,
  `condition_id`, and `attempt_id`.

These layers keep campaign methodology and evidence ownership in IVal
while leaving physics engines, dataset conversion, hardware control, and
official benchmark scoring in their source repositories.

`CampaignExecutor` now makes a frozen plan authoritative: every planned
attempt is executed once, committed with its plan digest, and skipped safely on
resumption when already recorded. Existing partial attempt directories are
refused rather than silently retried. Declarative `ival.campaign.v1`
maps compile into the same immutable plan format.

An existing frozen plan can also be loaded directly for recovery or execution,
without recompiling the source specification:

```bash
uv run --locked python -m ival.cli --frozen-plan campaign-plan.json \
  --execute-mock --output runs/recovered --audit
```
