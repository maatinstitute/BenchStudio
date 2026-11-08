# Episode evidence for interactive benchmarks

An executable Benchmark can use these optional contracts without changing its
native environment loop, inference API or evaluator. Import with `import
benchstudio as bs`.

- `bs.EpisodeIsolation(reset=hook)` calls `hook(system, case_id)` before yielding
  the native system. A reset error prevents entry into the episode.
- `bs.EpisodeIsolation(factory=hook)` enters the caller's context manager returned
  by `hook(case_id)`. It yields a fresh system and delegates cleanup on success or
  exception to that context manager.
- `bs.EpisodeIsolation(stateless=True)` is an explicit caller declaration.

Use `with isolation.activate(system, case_id) as native:` inside the existing
benchmark backend. No hidden reset method is discovered. These contracts do not
attest that model caches, remote services or external workers actually reset.
They do not allocate simulators or load checkpoints.

`bs.ActionBatch(observation, proposed, applied_indices)` snapshots serializable
native evidence. Indices identify proposal entries confirmed applied, in order;
a truncated chunk retains its unused proposals. If an environment transforms,
clips or rejects commands, retain its actual native action journal too: indices
alone do not prove actuator values or physical displacement. There is no inferred
unit conversion or automatic instrumentation.

`bs.EpisodeOutcome(completed, goal_reached=None, constraints_satisfied=None)` keeps
execution completion distinct from native goal and constraint verdicts. Unknown
checks remain None. `bs.EpisodeCoverage(planned, observed)` rejects duplicate or
out-of-calendar identities and exposes missing episodes. Completion does not
establish coverage, safety or scientific validity.

Excalidraw consumes these contracts in its existing executable benchmark. Robotics
backends may adopt them without changing their success semantics, release gates,
reserved identity handling or native process boundaries. No live robotics
qualification has been performed by these synthetic contract tests.
