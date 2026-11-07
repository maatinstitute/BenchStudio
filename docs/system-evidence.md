# System-run evidence

A run is identified by the **entire system graph**, not one model ID. The
portable offline format is a directory with `system.json`, `trials.jsonl`,
and `manifest.json` declaring SHA-256 hashes of the other two.

Trial identity freezes task revision, scenario, condition, seed, repetition,
environment revision, protocol identity and native evaluator revision.

`Trial.success` is optional; world models may provide continuous metrics only.
A failed or incomplete execution is NOT a policy failure. Only completed,
authoritative, explicitly scored outcomes qualify for a binary success
comparison. Scores are accepted as source assertions, not independently
reconstructed from missing physics or robot evidence.

`open_run(path)` parses and verifies existing evidence. No model or
simulation is loaded or rerun. `TrialKey` is designed for pairing systems
under matched evaluation conditions (PR #14).

**RoboCurve / Inspect Robots interoperability:** Inspect Robots already owns
real-robot eval execution and versioned EvalLogs. BenchStudio should ingest
their recorded outputs through a dedicated, tested source adapter, *not*
duplicate their graders or claim generic logs are inherently equivalent to
BenchStudio trials. This initial PR defines the strict target format; a
source-specific mapping must preserve scorer authority and provenance.
