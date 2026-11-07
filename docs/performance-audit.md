# CPU performance audit

The first measured targets are BenchStudio's own metadata/trace paths. vLLM
inference stays delegated to its upstream engine. No real models, simulator,
GPU, physical agents or scientific confirmation identities are used here.

## Interaction traces

Reproduce with `python scripts/benchmark_trace_audit.py` after installation.
The fixture contains 200 components, 199 declared connections and 4,000 events
across 20 synthetic trials. Each event links to its preceding component.
The script times validation only, excluding fixture construction, and emits a
cProfile summary. It asserts the valid verdict and exact observed connections.

On the local Python 3.12 environment, median of five runs:

| Implementation | Audit time | Profiled function calls |
| --- | ---: | ---: |
| Linear declared-connection search | 65.8 ms | 502,741 |
| Indexed connection lookup | 3.3 ms | 32,903 |

The old profile included 402,179 Connection equality checks. An index keyed by
source/output/target/input removes the per-event linear scan and reuses the
already validated Connection objects. Output ordering still follows the system's
connection declaration. Event/parent, port, trial, clock and cycle checks remain.
Auxiliary space increases by an index proportional to the declared edge count.

A regression limits equality comparisons on the large fixture, avoiding a flaky
wall-clock assertion; it failed on the previous implementation. Another checks
that wrong ports still produce both relevant issues and never become observed
connections. Existing trace rejection tests run alongside them.

These timings describe one synthetic metadata workload, not live swarm latency,
inference speed or production throughput. They are not guaranteed on other
machines or graph shapes. The checked-in script prints its fixture size and
measurement boundary so comparisons can be repeated.

## Language choice

This measured bottleneck came from repeated searching and object construction.
Indexing resolves it without a native build or a second implementation to keep
consistent. Rust remains a candidate for CPU work shown by representative
profiles to dominate after algorithmic fixes, for example high-volume ingestion
or serialization. A native port must preserve malformed-input rejection, error
ordering, event lineage and canonical identities against the Python reference.
No Rust component or claimed Rust speedup is added by this change.

For immutable identity lookup, see the separate reproducible microbenchmark in
`scripts/benchmark_identity_overhead.py` and docs/vllm-backend.md. That test
measures cached metadata hashing only.
