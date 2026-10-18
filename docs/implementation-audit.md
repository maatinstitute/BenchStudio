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
| WorldEpisode binding | Boundary verified | The optional reference validator is used when installed; the strict local fallback reports missing canonical metadata instead of fabricating it. |
| RoboChallenge integration | Observe-only verified | Opaque observation/action digests and acknowledgments are validated; safety, execution, and official scoring remain external. |
| AlpaBridge integration | Telemetry verified | Driver telemetry schema and deadline/load-failure audits are dependency-free; AlpaSim serving remains external. |
| External simulator backends | Not yet end-to-end | Mock and trace-replay facades are included. MuJoCo, Genesis, Isaac Lab–Arena, and physical execution require their pinned runtimes and approved assets. |
| SmolVLA/DM0.5 parity | Harness ready, external run pending | The parity and schedule contracts are implemented; no checkpoint is bundled or silently downloaded. |
| CI workflow | Prepared locally, not uploaded | `.github/workflows/ci.yml` exists locally. GitHub rejected its upload because the current OAuth token lacks workflow scope; source and smoke tests are published. |

The repository remains private and proprietary. External benchmark scoring,
physical safety, emergency stops, and hardware authorization are intentionally
not inferred from BenchStudio evidence.
