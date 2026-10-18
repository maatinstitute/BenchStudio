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

The shared SDK also exposes lifecycle and replay-timing checks, embodiment
signal mappings, score-coverage audits, and conservative missing-outcome
bounds. These are analysis and conformance primitives: they do not replace a
simulator, official scorer, robot driver, or WorldEpisode implementation.

Simulator implementations register an `AdapterDescriptor`. Optional simulator
dependencies are probed only when readiness is requested; the mock adapter
therefore remains usable in a clean Python environment.

## Replay boundary

`benchstudio.replay` accepts the `robot_joints` NDJSON stream emitted by URDF
Studio-style episode traces. It exposes that sequence through the same `Policy`
contract as a live VLA. `ReplaySimulator` is deliberately a validation facade,
not a physics engine; the next production adapter should implement the same
contract for MuJoCo, Genesis, or RoboChallenge's approved simulator.
