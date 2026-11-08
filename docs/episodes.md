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

## Integration with the existing engine

Return `benchstudio.backends.CaseResult(completed, native_output,
episodes=(bs.EpisodeRecord(case_id, outcome, batches, isolation_mode), ...))`
from the existing backend. `completed` describes the execution group; each record
identifies an experimental unit in that group's frozen benchmark calendar.

The engine rejects duplicate or wrong-group episode identities before accepting
that batch. It owns common `episodes.jsonl` persistence and
`episode_coverage.json`, including partial runs and failures. Inspect
`pipeline.episode_records` and `pipeline.episode_coverage` in memory. Coverage
counts returned evidence, not native success or independent verification.
Backends that return no episode evidence remain supported and have no observed
common episode records; the engine does not infer them from process completion.

Native result objects and analyses are returned unchanged. Benchmarks retain
native action journals; they no longer need their own serializer for these common
records. Isolation stays at the native episode boundary: an execution group may
contain many episodes, so resetting once per process would be incorrect.

This file format is common evidence, not a second causal SystemEvent stream.
No component clock or causal lineage is invented from the order of action batches.
