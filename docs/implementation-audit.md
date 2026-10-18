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
| Evidence integrity | Verified locally | Artifact manifests, sibling anchors, external digest verification, and safe archive extraction are implemented. A remote signature service is not claimed. |
| Policy lifecycle and timing | Verified as contracts | Lifecycle, action semantics, clock domains, queue/drop/deadline, and replay conformance validators are tested. |
| Model capability declarations | Verified as data contracts | VLA, planner, world-model, monitor, timing, memory, streaming, and caching fields are represented and validated. |
| Inference efficiency | Verified as instrumentation | Latency, observation age, action chunks, resource points, overhead, and Pareto helpers are implemented; no production checkpoint result is claimed. |
| Paired statistics | Verified | Exact binomial and discordance intervals, matched deltas, missingness, and standard errors are exposed in analysis results. |
| Sim-to-real fidelity | Analysis-ready | Transfer gaps, failure-category agreement, observation-age summaries, and ranking concordance are implemented; physical data is not present. |
| Robustness and recovery | Analysis-ready | Counterfactual pairing, confirmation plans, missing-outcome bounds, and recovery summaries are implemented; no disturbance campaign has been run. |
| Frozen counterfactual plans | Implemented | Nominal and intervention branches share frozen pair identities, receive deterministic branch IDs, and carry a separately validated counterfactual plan digest. |
| Counterexample search integrity | Implemented | Search plans can be serialized and independently validated for case identity, scenario consistency, and digest integrity before confirmation. |
| WorldEpisode binding | Boundary verified | The optional reference validator is used when installed; the strict local fallback reports missing canonical metadata instead of fabricating it. |
| RoboChallenge integration | Observe-only verified | Opaque observation/action digests and acknowledgments are validated; safety, execution, and official scoring remain external. |
| AlpaBridge integration | Telemetry verified | Driver telemetry schema and deadline/load-failure audits are dependency-free; AlpaSim serving remains external. |
| External simulator backends | Adapter boundary and readiness only | Mock and trace-replay facades are included. Backend capability declarations and entry-point discovery now gate authority-sensitive construction, while MuJoCo, Genesis, Isaac Lab–Arena, and physical execution still require their pinned runtimes and approved assets. |
| Frozen backend requirements | Implemented | Environment declarations can pin an adapter and required authority capabilities; `CampaignExecutor` rejects unmet or unavailable requirements before scheduling attempts. |
| Sim-to-real statistical uncertainty | Implemented for matched records | Transfer reports preserve missing outcomes and now include an exact paired discordance confidence interval alongside the point gap and standard error. |
| RoboChallenge observe-only evidence | Implemented at protocol boundary | Validated opaque observation/action bytes are retained as canonical base64 plus SHA-256 digests; execution and official scoring remain external. |
| End-to-end campaign audit | Implemented | `CampaignExecutor.audit()` reads the append-only ledger and validates frozen-plan completeness, artifact verification, and claim prerequisites in one path. |
| Distributed lease recovery | Implemented for filesystem workers | Expired leases are reclaimable by the next worker, active leases can be renewed by their owner, and ownership checks remain enforced. Physical jobs still require explicit no-retry policy. |
| Campaign evidence bundles | Implemented | Deterministic, content-addressed ZIP bundles include frozen plans, ledgers, manifests, and attempt evidence; extraction rejects symlinks and traversal paths. |
| CLI campaign workflow | Implemented | Declarative mock execution can now audit its ledger and write the immutable campaign bundle from one command. |
| SmolVLA/DM0.5 parity | Harness ready, external run pending | The parity and schedule contracts are implemented; no checkpoint is bundled or silently downloaded. |
| CI workflow | Prepared locally, not uploaded | `.github/workflows/ci.yml` exists locally. GitHub rejected its upload because the current OAuth token lacks workflow scope; source and smoke tests are published. |

The repository remains private and proprietary. External benchmark scoring,
physical safety, emergency stops, and hardware authorization are intentionally
not inferred from BenchStudio evidence.
