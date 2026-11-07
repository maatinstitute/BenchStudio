# AlpaBridge capability migration

Reviewed source: AlpaBridge main at
`abf547bbeef860d9c05e038a9cc6b84eae7e62a1` (README and source inventory).
BenchStudio can become the common evaluation entry point while retaining
backend-specific runtime adapters. This async scheduler is new implementation;
no AlpaBridge source was copied in this change.

| Capability | BenchStudio status after this change | Required before replacing AlpaBridge |
| --- | --- | --- |
| Python system evaluation and paired analysis | Implemented with synthetic checks | Qualify native runtime evidence |
| Bounded async trials, member groups, named resource slots | Implemented with synthetic checks | Measure representative throughput and latency |
| AlpaSim live driver/session lifecycle | Existing integration helpers; scheduler alone does not provide the driver | Native service adapter and session parity |
| Camera calibration/freshness, route and trajectory semantics | Existing integration helpers | Preserve native contract controls and retained conformance fixtures |
| AlpaSim installation, scenes, Docker services and readiness | Not supplied by this scheduler | Migrate setup/readiness/launch paths independently |
| Seven backend policies and native checkpoint dependencies | Not migrated by this change | Pin and validate each desired backend |
| Batch retries, support bundles and retained run evidence | New async path aborts without partial run persistence | Durable per-trial records and explicit retry policy |

The new common core does not yet justify retiring AlpaBridge. A migration must
preserve its successful native paths, failure controls and provenance. Synthetic
scheduler tests cannot establish those equivalences. Frozen evidence remains
unchanged; future native validation needs its own authorization and environment.
