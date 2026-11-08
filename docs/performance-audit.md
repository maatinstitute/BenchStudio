# CPU performance audit

The first measured targets are BenchStudio's own metadata/trace paths. Provider
inference stays with its native implementation. No real models, simulator,
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
`scripts/benchmark_identity_overhead.py`. That test measures cached metadata
hashing only.

## Result export

Reproduce with `python scripts/benchmark_result_export.py`. The fixture runs a
plain Python identity function on 4,000 scalar examples, compares its run with
itself, and exports each trial. No learned model or environment is involved.
The timed export includes Trial.to_dict plus sorted, finite JSON encoding;
fixture construction, evaluation and comparison are outside the timed export.
The script separately profiles the full CPU path to expose other costs.

Local Python 3.12, median of five export runs:

| Implementation | 4,000-record export |
| --- | ---: |
| Recursive dataclass conversion | 41.1 ms |
| Explicit scalar/schema conversion | 23.0 ms |

Trial's schema contains validated scalars and two mappings (identity fields and
numeric metrics). Recursive deep copying is unnecessary. The new conversion
copies both mappings and retains the exact serialized fields and values. A
regression compares sorted JSON bytes against the previous dataclass conversion
for completed, unscored and failed records, checks round trips, and verifies that
changing an exported mapping cannot mutate the source. Read-only metric mappings
also export correctly. Constructor and import validation remain in place.

The full-path profiler's function-call count fell from approximately 797,000 to
513,000 on this fixture. This is a CPU metadata/export result, not an inference
speedup or evidence of an end-to-end production acceleration. The remaining
profile includes record construction/validation, pairing and JSON encoding;
those require representative larger workloads before a native port is justified.


## Repeated digest format validation

The result-export script also compares the same regex validator with and without
an LRU cache of 256 valid plain strings. It measures fresh benchmark construction,
evaluation, paired comparison, export and a digest of the complete output. Thirty
samples per variant alternate their execution order and clear the cache before
each sample. Local Python 3.12 medians were 70.4 ms uncached and 64.3 ms cached
(about 9% on this synthetic workflow). All 60 outputs had the same digest.
The script also exposes the tradeoff: 4,000 all-unique digest checks took about
1.77 ms uncached versus 2.47 ms cached in a separate format-only measurement.
This cache helps repeated system/protocol identities, not all-unique inputs.
A tracemalloc snapshot retained approximately 54 KB for 256 freshly allocated
strings and cache bookkeeping on this interpreter (not an RSS memory bound).
Timings vary; these are not inference or production throughput measurements.

Only lowercase SHA-256 **format validation** is cached. File contents are still
hashed on every existing verification path; no file integrity check, authority
flag, qualification or release decision is cached. Invalid values still raise,
exceptions are not cached, and string subclasses follow the uncached validator
without custom hashing or string conversion. Tests cover invalid types/content,
subclass behavior and the 256-entry bound. Profiled full-path calls decreased
from roughly 513,000 to 481,000.

A separate candidate retained every benchmark TrialKey for later runs. It helped
reuse but slightly regressed the first fresh workflow and retained memory
proportional to benchmark size. That candidate was discarded. The remaining
record validation, comparison and JSON encoding costs are visible in the script;
being measurable alone does not justify removing validation or adding a second
native implementation. Representative workloads and output/rejection parity
are required before further optimization or a Rust port.
