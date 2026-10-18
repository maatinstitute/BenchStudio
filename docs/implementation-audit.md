# BenchStudio implementation audit

This is a current-state audit of the roadmap in the private development
repository. “Verified” means covered by a local test or a directly inspected
artifact. It does not mean that an external simulator, checkpoint, or robot
has been evaluated.

| Capability | Current status | Evidence / boundary |
| --- | --- | --- |
| Frozen campaign execution | Verified | `CampaignExecutor`, append-only `AttemptLedger`, atomic cross-worker ledger commits, leases, cancellation, resumable evidence, explicit completed/failed/missing episode denominators, pre-scheduling adapter/reproducibility validation, duplicate-safe parity checks, fail-closed artifact verification with symlink/path containment checks, strict counterfactual evaluator validation, independently loaded frozen plans and scorer outcomes, offline artifact and claim-type-aware campaign CLI verification, and 219 tests. |
| Stable paired identities | Verified | `pair_id` is shared across enabled environments; `environment_id` is frozen in `AttemptKey` and manifests. |
| Declarative protocol | Verified | `benchstudio.campaign.v1` compiles into a plan carrying the frozen `(P,M,S,X,D,O,R)` envelope and source digest. |
| Scenario identity | Verified | `ScenarioPack` and deterministic content-addressed archives bind task revisions, assets, initial conditions, and success criteria. |
| Evidence integrity | Verified locally | Artifact manifests, sibling anchors, external digest verification, optional detached Ed25519 signatures for manifests and runtime receipts, and safe archive extraction are implemented. Key custody and any remote trust service remain external. |
| Runtime execution receipts | Implemented | Each run writes a digest-verifiable receipt recording the frozen run/attempt/plan identity, worker, backend, clock domain, execution interval, and environment fingerprint; receipts are included in artifact manifests. |
| Policy lifecycle and timing | Verified as contracts | Lifecycle, action semantics, clock domains, queue/drop/deadline, and replay conformance validators are tested. |
| Model capability declarations | Verified as data contracts and evidence | VLA, planner, world-model, monitor, timing, memory, streaming, and caching fields are represented, validated before execution, and persisted in registry-backed run manifests. |
| Model adapter registry | Implemented | Policy adapters declare capabilities and dependencies, support optional entry-point discovery, can be instantiated directly from frozen model declarations, and include a strict external JSON command bridge for independent policy runtimes. |
| Inference efficiency | Verified as instrumentation | Latency, observation age, action chunks, resource points, overhead, Pareto helpers, and concrete synchronous/asynchronous/streaming/cached policy execution strategies are implemented; no production checkpoint result is claimed. |
| Paired statistics | Verified | Exact binomial and discordance intervals, matched deltas, missingness, and standard errors are exposed in analysis results. |
| Sim-to-real fidelity | Analysis-ready | Transfer gaps, failure-category agreement, observation-age summaries, and ranking concordance are implemented; physical data is not present. |
| Benchmark validity provenance | Implemented | Frozen validity records cover task revision, dataset lineage, contamination review, exclusions, early termination, metric scope/revision, and metric stability; comparative audits gate invalid records. |
| Calibration provenance | Implemented at protocol boundary | Camera, action-transform, controller, physical-parameter, and clock calibration identities can be frozen per environment, compared for compatibility, and persisted in run manifests. |
| Robustness and recovery | Analysis-ready | Counterfactual pairing, frozen branch-lineage audits, confirmation plans, missing-outcome bounds, and recovery summaries are implemented; no disturbance campaign has been run. |
| Frozen counterfactual plans | Implemented | Nominal and intervention branches share frozen pair identities, receive deterministic branch IDs, and carry a separately validated counterfactual plan digest. |
| Counterfactual execution | Implemented | `execute_counterfactual_plan()` evaluates nominal and intervention branches through an external evaluator, preserves frozen branch lineage, writes deterministic evidence incrementally, and leaves missing or failed branches explicit for recovery. |
| Counterexample search integrity | Implemented | Search plans can be serialized and independently validated for case identity, scenario consistency, and digest integrity; `execute_search_plan()` persists deterministic case results and exposes only observed failures as confirmation candidates. |
| Counterexample confirmation | Implemented | `execute_confirmation_plan()` evaluates an independent holdout matrix, links results to the frozen search digest, and records failure reproduction separately from discovery evidence. |
| WorldEpisode binding | Boundary verified | The optional reference validator is used when installed; the strict local fallback reports missing canonical metadata instead of fabricating it. |
| RoboChallenge integration | Observe-only verified | Opaque observation/action digests and acknowledgments are validated; safety, execution, and official scoring remain external. |
| AlpaBridge integration | Telemetry verified | Driver telemetry schema and deadline/load-failure audits are dependency-free; AlpaSim serving remains external. |
| External simulator backends | MuJoCo, Gymnasium, and external-process boundaries implemented; runtimes optional | Lazy adapters expose control/reset, state, timing, termination, and caller-supplied success semantics. Frozen plans can instantiate declared adapters through the registry, including a persistent JSON-line process bridge. The `mujoco`/`gymnasium` packages and pinned benchmark assets remain optional; Genesis, Isaac Lab–Arena, and physical execution still require their own runtimes and approvals. |
| Frozen backend requirements | Implemented | Environment declarations can pin an adapter and required authority capabilities; `CampaignExecutor` rejects unmet or unavailable requirements before scheduling attempts. |
| Adapter readiness reporting | Implemented | The CLI reports optional dependency availability and declared simulator/model capabilities before execution. |
| Registry-backed CLI execution | Implemented | `--execute-registry` instantiates the model and simulator adapters declared by the frozen campaign plan after readiness validation. |
| Sim-to-real statistical uncertainty | Implemented for matched records | Transfer reports preserve missing outcomes and now include an exact paired discordance confidence interval alongside the point gap and standard error. |
| RoboChallenge observe-only evidence | Implemented at protocol boundary | Validated opaque observation/action bytes are retained as canonical base64 plus SHA-256 digests; execution and official scoring remain external. |
| End-to-end campaign audit | Implemented | `CampaignExecutor.audit()` independently rechecks artifact manifests and frozen runtime receipt identity, then validates ledger completeness, calibration compatibility, and claim prerequisites in one path. |
| Outcome provenance persistence | Implemented | Plan-bound `OutcomeLedger` persists official, declared, or supplementary scorer records with schema, digest, duplicate, and frozen-attempt validation; executor audits reopen it automatically. |
| Audited evaluation reports | Implemented | Reports can serialize campaign audit decisions, outcome provenance, and paired uncertainty together, preserving qualified/unsupported claim context offline. |
| Distributed lease recovery | Implemented for filesystem workers | Expired leases are reclaimable by the next worker, active leases can be renewed by their owner, ownership checks remain enforced, and ledger commits are serialized with a cross-process file lock so stale worker state cannot duplicate an attempt. Physical jobs still require explicit no-retry policy. |
| Multi-worker campaign execution | Implemented | `CampaignExecutor.run_parallel()` assigns frozen attempts through filesystem leases and returns a plan-ordered aggregate after all workers refresh the shared ledger. |
| Scheduler batch dispatch | Implemented | `CampaignExecutor.run(attempt_ids=...)` accepts only IDs from the frozen plan, enabling external GPU/container schedulers to dispatch explicit batches while retaining ledger recovery and evidence checks. |
| Checkpoint provenance | Implemented | Frozen checkpoint digests, model adapters, architectures, and robot profiles are copied into attempt manifests without copying private adapter configuration paths. |
| Campaign evidence bundles | Implemented | Deterministic, content-addressed ZIP bundles include frozen plans, ledgers, manifests, and attempt evidence; extraction rejects symlinks and traversal paths. |
| Artifact publication | Implemented | `ArtifactStore`, `LocalArtifactStore`, and vendor-neutral `HttpArtifactStore` publish deterministic campaign bundles by digest with atomic local writes and idempotent retry behavior; cloud credentials and authorization remain external. |
| CLI campaign workflow | Implemented | Declarative mock or registry execution can audit its ledger, write immutable bundles, distribute frozen attempts with `--workers`, and publish to local or HTTP artifact stores from one command. |
| SmolVLA/DM0.5 parity | Harness ready, external run pending | The parity and schedule contracts are implemented; no checkpoint is bundled or silently downloaded. |
| CI workflow | Prepared locally, not uploaded | `.github/workflows/ci.yml` exists locally. GitHub rejected its upload because the current OAuth token lacks workflow scope; source and smoke tests are published. |
| Python compatibility | Locally verified | Python 3.10.12 compiles and imports the package; the full pytest suite runs under the configured Python 3.13 environment. |

The repository remains private and proprietary. External benchmark scoring,
physical safety, emergency stops, and hardware authorization are intentionally
not inferred from BenchStudio evidence.
