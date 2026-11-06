# Refinement/Refresh v3 launch qualification

Enable this guard in a declarative campaign under
`experiment.refinement_v3` (frozen as `P.experiment.refinement_v3`).
The declaration contains:

- `stage: "confirmation"`.
- `model: "pi0.5"` or `model: "smolvla"`.
- `evaluator_horizons`: the nonempty mapping of qualified suites to their
  frozen step limits. For multiple suites, each attempt must identify its suite
  in attempt metadata or the imported source row. A conflicting per-attempt
  step limit blocks launch.
- `runtime`: lowercase SHA-256 values keyed by `runner`, `checkpoint`,
  `simulator_stack`, `renderer`, `assets` and `normalization`.

Compile and review the plan before authorizing it. Supply a qualification
directory to `--qualification-directory` and obtain the SHA-256 of
`approval.json` directly from the approver for
`--qualification-approval-sha256`. The Python executor takes the same
values as `qualification_directory` and `trusted_approval_sha256`.
The launch check runs before an attempt initializes a policy or simulator.

The directory contains:

- `runtime.json`: the exact runtime identity mapping above, independently
  captured by the deployment tooling from the selected environment before
  launch. BenchStudio compares these observations to the frozen declaration.
  Collecting and verifying live process provenance remains the native launcher’s
  responsibility. An operator-authored copy of the expected mapping is not
  runtime evidence.
- `engineering_preflight.json` and `evaluator.json`, each with
  `"passed": true` and the evidence reviewed by the approver. The evaluator report
  must meet the semantic contract below. For π0.5, also
  supply `stock_parity.json` and `g02.json`.
- `approval.json`: `schema` is `benchstudio.refinement_v3_approval.v1`,
  `plan_digest_sha256` is the frozen plan digest, and `evidence` maps each
  required report's stem to the SHA-256 of its exact file bytes. Approve the
  report content independently. The guard verifies the authorization and
  its bindings, rather than rerunning those diagnostic checks.

## Capturing runtime and replay evidence in the native process

Call `capture_native_runtime` from
`benchstudio.integrations.native_evaluator_evidence` after the evaluator has
imported its dependencies and made its renderer current. Pass the actual
imported module objects keyed by their distribution names, and the paths
selected by the evaluator, grouped under `runner`, `checkpoint`, `assets`,
and `normalization`. Use stable logical file names as the group keys.
Write the returned `identity` mapping as `runtime.json` and retain the
full capture separately. It records both distribution and imported versions,
the hashes and resolved paths of imported files, and OpenGL vendor, renderer,
and version. Compare the full capture when a fingerprint changes.

For a replay fixture, freeze reset and post-action frame signatures from a
reviewed reference using `native_frame_signature`, together with its saved
actions. Open a fresh native environment and pass its restore and step
callbacks to `replay_native_fixture`. Each callback supplies `state`,
`observation` (named fields), `native_success`, `stop_reason`, and
`recorded_success` (null until an outcome exists). Preserve array dtype and
shape in the JSON representation used by both captures. Keep the same
serialization and renderer in both captures.

The diagnostic identifies the first differing tick, including reset at tick
zero, and lists observation fields, state, or outcome signals that changed.
A passing replay returns a fixture for `build_evaluator_report`. A failed
replay returns differences and no qualification fixture. The native adapter
still owns simulator lifecycle, outcome extraction, and goal verification.

## Evaluator qualification

For each planned suite, capture fixtures with the pinned native evaluator
using scripted actions or version-matched replay from diagnostic-only states.
Use the same environment, horizon and outcome-recording path used by the
confirmation runner. The independent checker evaluates the frozen task goal
against each captured state, without calling the evaluator's success function.
The RoboPAD single-predicate probe inspired the negative and positive
controls. Its historic output cannot substitute for a qualification report.

Generate `evaluator.json` using
`benchstudio.analysis.evaluator_qualification.build_evaluator_report`.
Pass the native runtime digest mapping, the independent checker's source
digest, the model, the raw fixtures, and the checker callback. Each fixture
contains `suite`, `task_id` (string), `kind`, `horizon` (step count),
`goal_spec_sha256` (e.g. BDDL bytes), `recorded_success`, and `samples`.
Samples contain a JSON `state` snapshot, zero-based `step`, the evaluator's
instantaneous `native_success`, and `stop_reason` (`null`, `goal`,
`horizon`, or `other`). An episode's outcome and its stop reason come
from the evaluator, independently of the goal checker. Preserve the raw
snapshots, scripts, and source identities for review.

Each suite requires a `goal_unmet` reset probe (null outcome), a
`goal_reached` episode starting from an unmet goal, and a
`horizon_timeout` episode with no goal reached. A stack supporting
non-goal early termination can also supply `non_goal_termination`.
The suite compares native and independent goal results at every recorded
step and checks the episode outcome against first attainment, including a
goal that was later lost. It distinguishes a stop due to the step limit
from a goal being reached. A native stack that exposes only `done` needs
to resolve that ambiguity in its adapter before it can pass this check.

The launch gate recomputes the case checks and compares suite coverage,
horizons, model, and runtime identity against the frozen plan. The native adapters
still own capturing the snapshots and evaluating the independent goal.

## Native π0.5 bridge

The guarded executor uses the persistent external policy bridge in synchronous
mode. Each predict request includes a unique `request_id`. The native process
must use its qualified compiled counter for that request and return:

```json
{"actions": [[0.0]], "metadata": {"denoising_attestation": {
  "request_id": "<request_id from predict>",
  "executed_steps": 2
}}}
```

The bridge rejects missing, stale or mismatched attestations before returning
the action chunk. The runner records an instrument failure and the executor
stops the campaign. A recorded incident also blocks resuming the same ledger.
Use a single worker for this protocol. The native OpenPI counter, the LeRobot
and LIBERO fixture adapters, and v3 paired analysis are separate work.
