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
- Refinement/Refresh result analysis: `benchstudio.analysis.result_metrics`
  is a direct port of `experiments/real_smolvla/result_metrics.py` from the
  same upstream commit. The source digest is
  `1b493b3643c89831757f7a3a5c75632b43512390d8eac12e6b1ce4960756d867`, and
  its regression-test digest is
  `f5fa8606d93263f5af0bd8799c640b62c83c2b139ea68da2598d227d96e06698`.
  The port preserves completed-outcome reconciliation, task/group identity
  checks, ledger-version timing provenance, and control-to-neural accounting.
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
- AlpaBridge: `benchstudio.integrations.alpasim_metrics` is a direct
  dependency-free port of `src/alpabridge/neutral/alpasim_metrics.py` from
  upstream commit `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`. Its source digest
  is `4e55083695485f7405f1bc6992699b16a747665513bd24036ddd29e67acc182c`.
  The port retains the original text/JSON/CSV loaders, metric aliases,
  threshold gates, run-count accounting, and explicit distinction between
  sensor-realistic evidence and official policy benchmark scores. It does not
  import AlpaSim or claim official scoring authority.
- URDF Studio / `urdf-ops`: `benchstudio.conformance.dataset_alignment` ports
  the dataset-alignment registry boundary from `backend/services/
  dataset_alignment.py` at upstream commit
  `561dc335cc7808f62d098dbaf7e05111ae444b28`. The source service digest is
  `d9eca077d025bd1b47718885629f73818912e81431a48fe88700ea6136a135cb` and
  the source model digest is
  `f6fddec7226dca951f4146ac9a264b1ed9e4c5a7c2615065f27bed0e846533e5`.
  The port preserves embodiment resolution, content-addressed mapping IDs,
  persistent registry round-trips, representation filtering, and fail-closed
  unnamed/mismatched dataset validation while injecting the owning runtime's
  kinematic fingerprint resolver.
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
