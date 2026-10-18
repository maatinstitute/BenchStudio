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

Simulator implementations register an `AdapterDescriptor`. Optional simulator
dependencies are probed only when readiness is requested; the mock adapter
therefore remains usable in a clean Python environment.

## Replay boundary

`benchstudio.replay` accepts the `robot_joints` NDJSON stream emitted by URDF
Studio-style episode traces. It exposes that sequence through the same `Policy`
contract as a live VLA. `ReplaySimulator` is deliberately a validation facade,
not a physics engine; the next production adapter should implement the same
contract for MuJoCo, Genesis, or RoboChallenge's approved simulator.
