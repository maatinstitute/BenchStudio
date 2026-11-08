# Specialist workflows

For the supported API, start with [the API guide](research-preview.md). These workflows are specialized and require their documented inputs and runtime dependencies.

# BenchStudio

BenchStudio is a research-use source-available library for experimental evaluation of AI systems,
especially interactive and embodied systems. The unit under evaluation is an
executable system: a model, a composed predictor/planner/controller, a group of
agents, or a complete robotics episode adapter.

Python objects configure systems and benchmarks. Versioned evidence formats
support storage and interoperability. Backends own execution semantics; the
benchmark owns its scoring definition. Comparisons preserve that distinction.

## Offline evaluation: predictions and components

```python
import benchstudio as bs
from benchstudio.analysis.claims import ClaimType
from benchstudio.replay_worker import ReplayLimits
from benchstudio.preparation import SourcePackage, check_imports

system = bs.System.from_callable(lambda x: 2*x, name="example", revision="r1")
benchmark = bs.Benchmark(
    "arithmetic", "fixtures-r1", inputs=[1, 2], targets=[2, 4],
    scorer=lambda output, target: bs.Score(success=output == target),
    evaluator_revision="exact-match-r1",
)
evaluation = bs.pipeline(
    system=system, benchmark=benchmark,
    config=bs.EvaluationConfig(run_id="example", output_dir="runs/example"),
)
print(evaluation.check().summary())
results = evaluation()
print(results.summary())
retained = bs.open_run("runs/example")
```

This executes arithmetic functions, not a learned model or simulator. Evaluator
authority defaults to false. Native adapters, checkpoints, state reset and
benchmark qualification still need explicit setup. For researcher-owned inference, configure native objects or endpoints and bind
their callables as described in [Native systems](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/native-systems.md). No
provider-specific model loader is maintained in the core package. Installed
systems and benchmark recipes resolve by name through
`System.from_backend` and `Benchmark.load`. The [system evaluation
guide](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/system-evaluation.md) covers the shared Python/CLI engine, dependency
checks, result retention and backend packaging. Native qualification remains a
separate requirement.

Use [paired system experiments](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/paired-system-experiments.md) to construct
an executable Workflow, replace a named component and compare variants through
`bs.pipeline("ablation", ...)`. The complete synthetic example is
`python examples/systems/paired_ablation.py`. Async execution and agent groups
are described in [async system execution](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/async-system-execution.md).
Declared component isolation alone does not establish a causal effect.

## Configure components using their native APIs

Configure a VLA policy, world model, agent workflow, inference engine or service
client directly using its own API.
BenchStudio does not insert inference defaults or maintain a mirror of its options:

```python
import benchstudio as bs

system = bs.System.from_callable(
    configured_system_function, name="candidate", revision="full-setup-r1",
    configuration=declared_setup,
)
print(system.describe())
evaluation = bs.pipeline(system=system, benchmark=benchmark, config=config)
results = evaluation()
```

The native function and its parameters remain under the researcher's control.
The optional declaration is visible and retained with results; omitted settings
are labeled opaque. It does not configure or certify the actual system. Any model
framework can be configured by its owner; native observations, actions and
predictions are preserved. See
[working native-object and endpoint patterns](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/native-systems.md).

## Complete interactive evaluations

An evaluation of LIBERO or AlpaSim is a calendar of episodes/scenes, conditions and
repetitions, not one policy prediction. Executable benchmarks bind that calendar
to native execution, outcomes and aggregation using the same engine. See
[benchmark protocols](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/benchmark-protocols.md) for experimental units versus
native execution groups, coverage, retention and the current LIBERO boundary.

## Installed simulator integrations

Installed integrations use the same callable pipeline and shared configuration:

```python
import benchstudio as bs

evaluation = bs.pipeline(
    "alpasim", model="route_following", alpasim_root="/opt/alpasim",
    scene_ids=("YOUR_INSTALLED_SCENE_ID",),
    config=bs.EvaluationConfig(output_dir="runs/alpasim", timeout=900),
)
print(evaluation.benchmark.describe())
print(evaluation.check().summary())
results = evaluation()
print(results.summary())
```

This requires the optional AlpaBridge integration and a provisioned native stack;
configuration checks do not qualify that stack. See [the integration guide](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/alpabridge-migration.md).
The researcher does not implement a backend, manage a worker or call per-case
methods. Integration authors have a separate [extension contract](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/execution-backends.md).

## Robotics evaluation pipeline

The robotics evaluation pipeline accepts task, model, environment, seeds and
evaluation conditions directly for registered robotics adapters:

```python
import benchstudio as bs

run = bs.pipeline(
    "robotics-evaluation",
    task={"id": "pick-cube", "revision": "fixture-v1"},
    model="mock",
    environment={"adapter": "mock-simulator", "kind": "simulator"},
    seeds=[7, 8],
    conditions=[{"id": "baseline"}],
    run_id="first-evaluation",
    output_dir="runs/first-evaluation",
    execution="mock",
)()
print(run.summary())
print(run.analyze().summary())
```

This is a synthetic API check. It does not load a robot policy or establish
simulator fidelity. Run the checked-in version with a fresh output directory:

```bash
python examples/direct_pipeline_mock.py runs/first-evaluation
```

The result separates execution accounting (`run.summary()`) from offline
evidence review (`run.analyze()`). BenchStudio freezes the named inputs into a
campaign plan and records its digest. Stable task revisions, checkpoint
identities, seeds, conditions, and environment configuration remain explicit
because they define what an evaluation means.

## Connect a real policy and environment

For a stack already supported through registered adapters, replace the mock
declarations with those adapters and set `execution="registry"`:

```python
import benchstudio as bs

evaluation = bs.pipeline(
    "robotics-evaluation",
    task={"id": "libero/spatial/task-0", "revision": "<pinned-task-revision>"},
    model={
        "adapter": "smolvla",
        "checkpoint": "sha256:<reviewed-checkpoint-digest>",
        "config": {"command": ["python", "your_policy_service.py"]},
    },
    environment={
        "adapter": "external_command",
        "id": "libero-local",
        "config": {"command": ["python", "your_environment_service.py"]},
    },
    seeds=[7, 8],
    conditions=[{"id": "baseline", "denoising_steps": 10}],
    run_id="smolvla-libero-baseline",
    output_dir="runs/smolvla-libero-baseline",
    execution="registry",
)
run = evaluation()
print(run.summary())
```

The named policy and environment adapters must already be installed and their
services must implement the JSON-line protocols documented by those adapters.
This is not an automatic Transformers-style checkpoint loader: the caller owns
the robot observation/action mapping, preprocessing, environment assets, and
runtime installation. See [the API comparison](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/transformers-comparison.md)
for the exact boundary and [the model bridge example](https://github.com/amtellezfernandez/BenchStudio/blob/main/examples/external_runtime/lerobot_smolvla_policy.py)
for a LeRobot-owned SmolVLA process.

To inspect an existing run without executing it again:

```python
import benchstudio as bs

audit = bs.pipeline(
    "campaign-audit", claim_type=ClaimType.SINGLE_RUN_OUTCOME
)("runs/first-evaluation")
print(audit.summary())
```

## Developer quick start

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

For a presentation-ready local demo, including the existing URDF Studio SO-101
robot performing a cube-lift evaluation in MuJoCo, run:

```bash
bash scripts/demo.sh /tmp/benchstudio-demo --serve
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
turning missing runs into zero scores. BenchStudio adds campaign accounting,
robustness evidence, matched transfer, and the RoboChallenge transport audit,
then serves the robot episode batch and evidence in the Eval Control Room at
`http://127.0.0.1:8765`. The generated files
under `/tmp/benchstudio-demo` remain inspectable evidence artifacts. If that
directory already exists, the script creates a timestamped sibling rather than
overwriting it. These fixtures demonstrate BenchStudio's execution and audit
boundaries; they are not physical-robot or model-quality results. BenchStudio
auto-detects a sibling `urdf-studio` checkout. Otherwise set
`URDF_STUDIO_ROOT=/path/to/urdf-studio`. Limit or reorder the requested backends
with `BENCHSTUDIO_SIMULATORS=mujoco`, `genesis`, or `mujoco,genesis`.

The included SO-101 batch is a contact-grasp diagnostic fixture. The staged URDF
keeps the upstream visual model and kinematics, retains only the exact fixed-
and moving-finger mesh collisions, and adds joint damping.
The policy is not allowed to weld or attach the cube. Multiple seeds vary cube
placement while preserving the policy, checker, and simulator parameters. A
failure is a first-class result: each episode records cube displacement and
lift, sampled contact and bilateral-retention frames, gripper target tracking,
failure timing, source hashes, and a bounded root-cause classification.

The ordinary rollout trace remains sampled at 50 Hz. BenchStudio therefore
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

Exercise parallel lease-owning workers with:

```bash
PYTHONPATH=src python examples/run_mock_workers.py --output runs/mock-workers --workers 3
```

This verifies shared lease ownership and exactly-once ledger accounting for a
local fixture campaign.

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

See [docs/architecture.md](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/architecture.md) for the integration boundary.
See [docs/implementation-audit.md](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/implementation-audit.md) for the
verified current state and the external integrations that remain intentionally
unclaimed.


## Replay a RoboPAD archive

Install BenchStudio into the Python environment that owns the pinned RoboPAD
LIBERO runtime and assets. From a BenchStudio checkout, use
`python -m pip install -e .` in that environment.

```python
import benchstudio as bs

pipeline = bs.pipeline("replay", source="./robopad_attempt.tar.gz")
results = pipeline()
print(results.summary())
```

The pipeline also accepts an extracted campaign folder. Pass
`episode="your-episode-key"` (using a key from your manifest) when the campaign
has multiple episodes. It verifies the archive records and consumed hashes,
checks the installed BDDL task asset, renders a fresh reset, and replays the
archived prefix and nominal base actions against the original saved states
and observations. Use `pipeline.check()` for the readiness report alone.
The full replay evidence is in `results.report`.

The equivalent command is `benchstudio-replay ./robopad_attempt.tar.gz --check`
for readiness or `benchstudio-replay ./robopad_attempt.tar.gz` for replay.
This first pipeline supports completed nominal base attempts from RoboPAD's
`validation_transfer_v1` format. It expects the native stack to be installed,
and compares the archived observation hashes exactly. Renderer drift can
appear as an image difference even when the recorded simulator state agrees.

### Archived environment requirements

Replay discovers the environment requirements stored by the archive producer.
Users do not write a JSON configuration or override those requirements. Runtime
mismatches block verified replay. Legacy archives without requirements are
reported as `legacy_unpinned`; reset success alone does not establish parity.
The archive format is an internal interchange contract, not the Python API.

### Replay with an independently trusted manifest

For a reviewed handoff, obtain the SHA-256 of `benchstudio-replay.json`
through a separate trusted channel and supply it to the pipeline:

```python
pipeline = bs.pipeline("replay", source=
    "robopad_attempt.tar.gz", trusted_manifest_sha256=reviewed_manifest_sha256
)
result = pipeline.run()
```

This mode requires a compressed archive, stages it in a private temporary
directory, checks the manifest against the supplied digest, and verifies the
runtime before replay. The CLI accepts the same value with
`--trusted-manifest-sha256`. The digest must come from the reviewer. Reading
it from the same archive would only check self-consistency.

### Run replay in a resource-limited worker

On Linux, pass limits when opening an archive. Both readiness and replay
then run in a separate process using the same installed Python environment:

```python
pipeline = bs.pipeline("replay", source=
    "robopad_attempt.tar.gz",
    trusted_manifest_sha256=reviewed_manifest_sha256,
    limits=ReplayLimits(wall_seconds=300, cpu_seconds=240),
)
result = pipeline.run()
```

The CLI enables the default limits with `--worker`. The worker has a
wall-clock deadline and Linux limits for CPU time, virtual address space,
open files, and individual file size. The supervisor kills the process
group on timeout. The existing archive extraction and report size limits
also apply. These limits do not isolate filesystem or network access and do
not cap GPU memory. Use a separately configured container or job sandbox
where those controls are required.


## Replay saved actions in LIBERO

Run BenchStudio from the pinned LIBERO environment that owns the task assets
and renderer. The public adapter imports LIBERO on demand. Select
`backend="lerobot"` for the reset and raw observation path used by RoboPAD, or
use the default `backend="native"` for direct LIBERO. Keep the backend, seed,
task, initial-state slot, and renderer consistent between captures.

```python
import json
from pathlib import Path

import numpy as np

from benchstudio.libero import LiberoAdapter, replay_libero

# Use the suite, task, initial state and seed from the recorded RoboPAD attempt.
adapter = LiberoAdapter("libero_spatial", task_id=0, initial_state_id=0, seed=42,
                        backend="lerobot")
actions = np.load("nominal_actions.npy", allow_pickle=False)
reference = adapter.capture(actions)
Path("libero-reference.json").write_text(json.dumps(reference), encoding="utf-8")

report = replay_libero(json.loads(Path("libero-reference.json").read_text()))
print(report["passed"], report["first_mismatch_step"], report["differences"])
```

Capture and retain the reference on the reviewed baseline stack before replay
on a candidate environment. Tick zero is the restored initial state. The
first later divergence identifies state, outcome signals, and observation
fields that changed. For arrays, comparison includes dtype, shape, and exact
bytes. The LeRobot path preserves the dtype of a NumPy action array.
A new capture from an archived action file is a new baseline, so
retain any original RoboPAD trace separately. Independent evaluator
qualification uses its own goal checker and outcome evidence.



### Preparing native programs

Use `SourcePackage` to verify declared source files before launching an external
Python entry point and create reproducible source archives. Use `check_imports`
for an explicit import diagnostic in a separate native interpreter, with retained
logs and genuine failure exits. See [native preparation](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/native-preparation.md).
These checks do not qualify a model or grant experimental execution permission.
