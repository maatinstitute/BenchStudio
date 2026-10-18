# Source attribution

BenchStudio uses source-backed adapters and explicit independent boundaries for
the following projects. Product runtimes are not vendored into this repository.

- WorldEpisode / `leWorldDataset`: the optional validator binding follows the
  published validator/preflight boundary. The replay fixture identifies
  `tools/replay_adapter_conformance.py` as its source basis and deliberately
  does not claim physics replay coverage.
- Refinement vs Refresh: `benchstudio.campaigns.refinement_plan` is a direct
  source-backed port of `experiments/make_evaluation_plan.py` at upstream commit
  `8c92e66c7ab19403822cb87908253260666fb3a6`. The source file digest is
  `a393a13580345b1a9fd31ba8cc4c02bb195807191570d330368f5fe53f165a5c` and its
  upstream test digest is
  `806efcaf489c92a34279aea60c0ff850dd803e45a68636be29a198c939475cc8`; its
  planner invariants are carried into `tests/test_refinement_plan.py`. The adapter
  preserves the upstream schema, canonical JSON, SHA-256 keyed ordering,
  schedule digest, external gates, and exclusive-write semantics; it then
  converts that exact schedule into `FrozenCampaignPlan`. The heavy
  CUDA/LeRobot runtime remains external.
- RoboPAD: `benchstudio.analysis.responsiveness` is a source-backed port of
  `experiments/metrics.py`, and `benchstudio.campaigns.outcome_plan` is a
  source-backed port of `experiments/outcome_plan.py`, from upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`. The source digests are,
  respectively, `b8bedc9cf2f0f93dda8203e48ad61cfeddd3662f6b3cdb6b7beec5138230593e`
  and `5c27df4d02e56ab1b116eb1b0786ff892e673d27fd517918ab185082b2485ba2`.
  Their invariants are carried into `tests/test_responsiveness.py` and
  `tests/test_outcome_plan.py`. BenchStudio exposes the ports through its
  analysis and campaign packages; external training, checkpoint, simulator,
  and official outcome authority remain outside the repository.
- URDF Studio, AlpaBridge, RoboPAD, refinement/refresh experiments, and
  `urdf-ops`: BenchStudio exposes independent contracts for scenario identity,
  lifecycle, campaign accounting, counterfactual lineage, and embodiment
  mapping. The `PolicySession` boundary is informed by AlpaBridge's session,
  modality, readiness, and latency behavior; it is a dependency-free contract,
  not a port of the AlpaBridge service. The AlpaBridge telemetry adapter reads
  the published v3 JSONL shape and preserves its latency-target, route-source,
  and model-load event semantics; it does not import or reimplement AlpaSim.
Product-specific runtimes remain external.

The optional `benchstudio.integrations.mujoco` adapter uses MuJoCo's public
Python API when the user installs the `mujoco` extra. It does not vendor the
runtime or assign official benchmark scoring authority to BenchStudio.

The optional `benchstudio.integrations.gymnasium` adapter follows Gymnasium's
public five-value `step` protocol and remains a generic environment boundary;
it does not claim LIBERO or another benchmark's task/scoring semantics.

The optional `benchstudio.integrations.genesis` adapter targets the public
Genesis World scene lifecycle and is dependency-lazy. Install the `genesis`
extra in the environment that owns Genesis; BenchStudio retains only the
temporal/evidence boundary and does not vendor Genesis or its assets.

The optional `benchstudio.integrations.isaaclab` adapter follows the public
manager-based environment reset/step contract, including vectorized resets,
termination signals, extras, and environment step timing. Isaac Lab remains
the owner of physics, environment lifecycle, and task scoring.

Any future source migration must preserve the original repository's notices,
third-party licenses, and historical evidence. The current BenchStudio
repository remains private and proprietary; this file is an engineering
provenance record, not a relicensing grant.
