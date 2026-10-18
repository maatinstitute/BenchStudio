# BenchStudio implementation audit

This is a current-state audit of the roadmap in the private development
repository. “Verified” means covered by a local test or a directly inspected
artifact. It does not mean that an external simulator, checkpoint, or robot
has been evaluated.

| Capability | Current status | Evidence / boundary |
| --- | --- | --- |
| Frozen campaign execution | Verified | `CampaignExecutor`, append-only `AttemptLedger`, leases, cancellation, resumable evidence, and 101 tests. |
| Stable paired identities | Verified | `pair_id` is shared across enabled environments; `environment_id` is frozen in `AttemptKey` and manifests. |
| Declarative protocol | Verified | `benchstudio.campaign.v1` compiles into a plan carrying the frozen `(P,M,S,X,D,O,R)` envelope and source digest. |
| Scenario identity | Verified | `ScenarioPack` and deterministic content-addressed archives bind task revisions, assets, initial conditions, and success criteria. |
| Evidence integrity | Verified locally | Artifact manifests, sibling anchors, external digest verification, optional detached Ed25519 signatures, and safe archive extraction are implemented. Key custody and any remote trust service remain external. |
| Policy lifecycle and timing | Verified as contracts | Lifecycle, action semantics, clock domains, queue/drop/deadline, and replay conformance validators are tested. |
| Model capability declarations | Verified as data contracts and evidence | VLA, planner, world-model, monitor, timing, memory, streaming, and caching fields are represented, validated before execution, and persisted in registry-backed run manifests. |
| Model adapter registry | Implemented | Policy adapters declare capabilities and dependencies, support optional entry-point discovery, and can be instantiated directly from frozen model declarations. |
| Inference efficiency | Verified as instrumentation | Latency, observation age, action chunks, resource points, overhead, Pareto helpers, and concrete synchronous/asynchronous/streaming/cached policy execution strategies are implemented; no production checkpoint result is claimed. |
| Paired statistics | Verified | Exact binomial and discordance intervals, matched deltas, missingness, and standard errors are exposed in analysis results. |
| Sim-to-real fidelity | Analysis-ready | Transfer gaps, failure-category agreement, observation-age summaries, and ranking concordance are implemented; physical data is not present. |
| Benchmark validity provenance | Implemented | Frozen validity records cover task revision, dataset lineage, contamination review, exclusions, early termination, metric scope/revision, and metric stability; comparative audits gate invalid records. |
| Calibration provenance | Implemented at protocol boundary | Camera, action-transform, controller, physical-parameter, and clock calibration identities can be frozen per environment, compared for compatibility, and persisted in run manifests. |
| Robustness and recovery | Analysis-ready | Counterfactual pairing, frozen branch-lineage audits, confirmation plans, missing-outcome bounds, and recovery summaries are implemented; no disturbance campaign has been run. |
| Frozen counterfactual plans | Implemented | Nominal and intervention branches share frozen pair identities, receive deterministic branch IDs, and carry a separately validated counterfactual plan digest. |
| Counterexample search integrity | Implemented | Search plans can be serialized and independently validated for case identity, scenario consistency, and digest integrity before confirmation. |
| WorldEpisode binding | Boundary verified | The optional reference validator is used when installed; the strict local fallback reports missing canonical metadata instead of fabricating it. |
| RoboChallenge integration | Observe-only verified | Opaque observation/action digests and acknowledgments are validated; safety, execution, and official scoring remain external. |
| AlpaBridge integration | Telemetry verified | Driver telemetry schema and deadline/load-failure audits are dependency-free; AlpaSim serving remains external. |
| External simulator backends | MuJoCo and Gymnasium adapter boundaries implemented; runtimes optional | Lazy adapters now expose control/reset, state, timing, termination, and caller-supplied success semantics. Frozen plans can instantiate declared adapters through the registry. The `mujoco`/`gymnasium` packages and pinned benchmark assets remain optional; Genesis, Isaac Lab–Arena, and physical execution still require their own runtimes and approvals. |
| Frozen backend requirements | Implemented | Environment declarations can pin an adapter and required authority capabilities; `CampaignExecutor` rejects unmet or unavailable requirements before scheduling attempts. |
| Sim-to-real statistical uncertainty | Implemented for matched records | Transfer reports preserve missing outcomes and now include an exact paired discordance confidence interval alongside the point gap and standard error. |
| RoboChallenge observe-only evidence | Implemented at protocol boundary | Validated opaque observation/action bytes are retained as canonical base64 plus SHA-256 digests; execution and official scoring remain external. |
| End-to-end campaign audit | Implemented | `CampaignExecutor.audit()` reads the append-only ledger and validates frozen-plan completeness, artifact verification, calibration compatibility, and claim prerequisites in one path. |
| Outcome provenance persistence | Implemented | Plan-bound `OutcomeLedger` persists official, declared, or supplementary scorer records with schema, digest, duplicate, and frozen-attempt validation; executor audits reopen it automatically. |
| Audited evaluation reports | Implemented | Reports can serialize campaign audit decisions, outcome provenance, and paired uncertainty together, preserving qualified/unsupported claim context offline. |
| Distributed lease recovery | Implemented for filesystem workers | Expired leases are reclaimable by the next worker, active leases can be renewed by their owner, and ownership checks remain enforced. Physical jobs still require explicit no-retry policy. |
| Campaign evidence bundles | Implemented | Deterministic, content-addressed ZIP bundles include frozen plans, ledgers, manifests, and attempt evidence; extraction rejects symlinks and traversal paths. |
| CLI campaign workflow | Implemented | Declarative mock execution can now audit its ledger and write the immutable campaign bundle from one command. |
| SmolVLA/DM0.5 parity | Harness ready, external run pending | The parity and schedule contracts are implemented; no checkpoint is bundled or silently downloaded. |
| CI workflow | Prepared locally, not uploaded | `.github/workflows/ci.yml` exists locally. GitHub rejected its upload because the current OAuth token lacks workflow scope; source and smoke tests are published. |
| Python compatibility | Locally verified | Python 3.10.12 compiles and imports the package; the full pytest suite runs under the configured Python 3.13 environment. |

The repository remains private and proprietary. External benchmark scoring,
physical safety, emergency stops, and hardware authorization are intentionally
not inferred from BenchStudio evidence.
