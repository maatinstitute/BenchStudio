# Research preview: supported API and capabilities

Version 0.1.0rc1 is an unpublished release candidate. The supported convenience
surface is `benchstudio.__all__` (15 names). Use `import benchstudio as bs`.
Older explicit root imports still resolve through `benchstudio.compat`; prefer
owning modules such as `benchstudio.processes` or `benchstudio.backends` for
extension/infrastructure work. Compatibility does not make every historical API
part of the preview's stability promise. No removal is introduced here.

Configure inference with its own provider/native API, then bind a System or pass
that native object to an installed executable Benchmark. BenchStudio does not
mirror vLLM settings or silently download models.

## Results

`native = evaluation()` preserves the existing native result and scientific
semantics. `report = evaluation.report()` gives a common view:

- `report.native`: original result object, unchanged;
- `report.coverage`: planned/observed/missing evidence identities, or None when
  unspecified; completion of a process does not establish episode coverage;
- `report.metrics`: retained offline per-trial metrics or explicitly exposed native
  metric mappings, without invented units, aggregation or cross-model pooling;
- `report.episodes`, `report.traces`, `report.outcomes`: returned common episode
  evidence; no inferred native constraints, safety or authority;
- `report.summary()`: native summary plus the evidence coverage boundary.

For a saved offline run: `bs.inspect_result(bs.open_run(path))`. For a native
reader, use its explicit installed backend with `bs.open_run(path, backend=...)`,
then inspect_result. A standalone native object has unknown common coverage
unless a calendar and EpisodeRecords are explicitly supplied. Native metrics
not exposed by its API stay absent. This does not convert specialized analyses
into a generic binary score. After execution failure, use retained partial
evidence; report() refuses to present a completed result.

## Execution support

Inspect `evaluation.capabilities` or `evaluation.check().capabilities` before
execution. check() also reports configuration errors without starting work.

| Path | Sync | Async/concurrency | Model batching | Timeout |
| --- | --- | --- | --- | --- |
| Offline callable | Subject to callable/scorer | arun(), if runtime permits | Explicit generate_batch only | Async path only |
| Executable benchmark/backend | Yes | Unsupported by this engine | Unsupported | Only when backend declares enforcement |
| Installed recipe | Recipe-owned | Recipe-owned | Recipe-owned | Recipe-owned |

This is a capability contract, not a performance claim. Unsupported interactive
scheduling is rejected rather than silently falling back. The preview does not
promise continuous batching, GPU scheduling or distributed native execution.

## Verified scope

| Integration | Evidence in this candidate | Remaining boundary |
| --- | --- | --- |
| Python callable evaluation | Actual arithmetic execution and saved-result reopening | No learned-model claim |
| Executable benchmark protocol | Stdlib state-machine calendar and common evidence | No simulator/model claim |
| Excalidraw | Real integration with test-double gym, isolation/error/truncation checks | Native gym and learned agent qualification pending |
| AlpaBridge/AlpaSim | Offline orchestration regression checks | Provisioned native runtime qualification pending |
| SmolVLA and pi0.5 paper recipe | Offline preparation/orchestration checks | Native environment/checkpoint/manifests/calendar, Protocol E, parity and compiled-count qualification pending |

Python runtime validation in this candidate is on 3.12; declared >=3.10
compatibility is not a substitute for runtime testing on other versions.
No simulator, GPU, model, reserved identity or scientific confirmation was used.

## License and distribution

Research Use License 1.1 applies, including the upstream-modification return and
restricted redistribution rules. This is not OSI open source. The repository is
private, no GitHub release is published, and PyPI publication or visibility
changes require a separate owner instruction. Source/contributor rights and
third-party notices still require review against the exact public release.
