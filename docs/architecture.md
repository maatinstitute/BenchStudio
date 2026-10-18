# BenchStudio architecture

BenchStudio owns measurement and provenance, not robot authority.

```text
policy adapter -> temporal scheduler -> simulator adapter
                       |
                       +-> evidence recorder -> manifest + JSONL + summary
```

`Policy` and `Simulator` are the stable contracts. The scheduler records
observation age, policy latency, action execution intervals, action prefix, and
termination state. A future RoboChallenge adapter should translate the public
benchmark interface while leaving safety checks, emergency stops, and official
scoring on the platform side.

Independent model runtimes may use the built-in `external_command` adapter. It
invokes a supplied executable without a shell, sends a versioned JSON request
for each inference, and accepts only a JSON action-chunk response. This is a
process boundary, not a claim that BenchStudio owns the model runtime.

The evidence schema is intentionally JSON-compatible and does not persist raw
images by default. Checkpoint paths and private environment values must be
represented by identifiers or digests, not copied into artifacts.

Trajectory comparison is available through `benchstudio.trajectory`. It uses
the same time-alignment and first-split approach as the existing URDF Studio
rollout analysis, while remaining independent of Pydantic and the web backend.

## Semantic and campaign boundaries

`benchstudio.conformance` provides a deliberately narrow adapter boundary for
WorldEpisode-like observations, action representations, clock capability
declarations, and scenario contracts. It reports missing or unverifiable
metadata instead of fabricating full world-revision conformance.

`benchstudio.campaigns` freezes the evaluation matrix before execution. A plan
separates `scenario_id`, `pair_id`, `condition_id`, and `attempt_id`; its digest
is carried into an append-only attempt ledger. Interrupted campaigns therefore
retain prior results and expose missing attempts without silently reassigning a
result to another condition.

`benchstudio.scenarios` represents a portable task pack by its task revision,
asset SHA-256 digests, initial-condition digest, and success-criterion version.
Campaign pair identities include the pack digest when supplied, so equal task
names do not imply equivalent evaluation worlds.

`CampaignExecutor` is the execution boundary for frozen plans. It creates one
evidence directory per attempt, commits only planned identities to the ledger,
and resumes by skipping already committed attempts. A partial directory without
a completed summary is surfaced as recovery-required rather than retried as a
new statistical sample.

The shared SDK also exposes lifecycle and replay-timing checks, embodiment
signal mappings, score-coverage audits, and conservative missing-outcome
bounds. These are analysis and conformance primitives: they do not replace a
simulator, official scorer, robot driver, or WorldEpisode implementation.

Counterfactual cells can pair a nominal attempt with an intervention branch at
the same transition index and `pair_id`. Deadline audits and critical-event
bookmarks make incomplete execution, timing misses, stale observations, and
unverified execution timestamps explicit without inferring unavailable facts.

Capability profiles, resource audits, transfer-gap estimates, and claim
validation keep the interpretation layer separate from raw outcomes. A
simulation result cannot become a real-world-transfer claim without physical
evidence and a declared transfer protocol; unsupported prerequisites are
reported rather than inferred.

Distributed workers use exclusive attempt leases and durable ledger commits.
The policy parity harness compares canonical action-chunk digests across a
reference and instrumented adapter. The RoboChallenge integration is
observe-only: it validates opaque message digests and records acknowledgments,
while execution, safety, and official scoring remain external.

The WorldEpisode integration is an adapter boundary: if the reference
validator is installed, BenchStudio delegates to it; otherwise it returns a
clearly labeled minimal-profile result rather than claiming full WorldEpisode
conformance. Replay timing includes a sourced zero-order-hold fixture based on
the upstream adapter-conformance cases, with no claim of contact-rich physics
coverage.
`CampaignExecutor` acquires and releases those leases around each attempt;
workers report leased-out and explicitly cancelled attempts separately from
completed and missing ones.

Paired summaries retain matched-unit counts, success gaps, numeric deltas, and
standard errors. `benchstudio.reporting` writes a dependency-free JSON-shaped
report and escaped offline HTML, suitable for artifact bundles and CI review.

Simulator implementations register an `AdapterDescriptor`. Optional simulator
dependencies are probed only when readiness is requested; the mock adapter
therefore remains usable in a clean Python environment.

Descriptors also expose explicit `BackendCapabilities`. Campaign tooling can
require properties such as `owns_physics`, `closed_loop`, or
`owns_official_scoring` before construction. This prevents a replay or mock
facade from being silently used as evidence-bearing simulator authority. A
MuJoCo, Genesis, Isaac Lab, or robot adapter may register through the
`benchstudio.simulators` entry-point group when its pinned runtime is supplied;
the core package does not install or pretend to provide those runtimes.

## Replay boundary

`benchstudio.replay` accepts the `robot_joints` NDJSON stream emitted by URDF
Studio-style episode traces. It exposes that sequence through the same `Policy`
contract as a live VLA. `ReplaySimulator` is deliberately a validation facade,
not a physics engine; the next production adapter should implement the same
contract for MuJoCo, Genesis, or RoboChallenge's approved simulator.
