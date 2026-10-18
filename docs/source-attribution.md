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
- Refinement/Refresh annotation agreement: `benchstudio.analysis.agreement`
  is a direct port of `review/agreement.py` at upstream commit
  `8c92e66c7ab19403822cb87908253260666fb3a6`; source digest
  `cbdc7ece57801c0c1bf32dcbd3cd2b5cdac521aafd8c739385d10b5ac26af0f2` and
  source-test digest
  `db526f5f630ae35a9c3d4ffcf36986ae1e3c41367844c54d8cd6f7495adbc806`.
  The neutral blind annotation fixture digest is
  `6f096153e5c8cbd5209d89cc42e1e2a9bba41291299153efc3cc3e481d4a4d32`.
  The port preserves frozen scope, evidence/locator/rationale requirements,
  label validation, kappa/agreement metrics, and disagreement records.
- Refinement/Refresh observation-age audit:
  `benchstudio.analysis.observation_age_audit` is a direct port of
  `experiments/tooling/audit_observation_age.py` at upstream commit
  `8c92e66c7ab19403822cb87908253260666fb3a6`; source digest
  `ffb18ad855d035d91b2eda60939426cb50c7618dcb45c77363619247bd718b75` and
  source-test digest
  `3394e7fee375e3cf5875c8707524085f1e3ece6f27662e8634fdf86296f2c89d`.
  The port preserves refresh cadence, held-observation identity, recursive
  field-hash reconciliation, paired episode identities, and first-divergence
  reporting; historical runtime data and policy-quality claims remain external.
- Refinement/Refresh paired protocol primitives: `benchstudio.analysis.
  refinement_protocol` extracts the dependency-free identity, keyed-seed,
  array/observation hashing, success-envelope, journal, development-schedule,
  and parity-report functions from `experiments/tooling/run_paired.py` at
  upstream commit `8c92e66c7ab19403822cb87908253260666fb3a6`; source digest
  `09fbef924edbf075ea245db6d59ba4e181785e0d3a2f66d632f264d82970458f` and
  source-test digest
  `256e0e6ebbe34f5930ba1afb8d1d9b153ee84bd3d00bb5b4dd0a80e9d1562313`.
  CUDA/LeRobot rollout execution and checkpoint ownership remain external.
- Refinement/Refresh result analysis: `benchstudio.analysis.result_metrics`
  is a direct port of `experiments/real_smolvla/result_metrics.py` from the
  same upstream commit. The source digest is
  `1b493b3643c89831757f7a3a5c75632b43512390d8eac12e6b1ce4960756d867`, and
  its regression-test digest is
  `f5fa8606d93263f5af0bd8799c640b62c83c2b139ea68da2598d227d96e06698`.
  The port preserves completed-outcome reconciliation, task/group identity
  checks, ledger-version timing provenance, and control-to-neural accounting.
- Refinement/Refresh ledger verification: `benchstudio.analysis.ledger_validation`
  is a source-backed port of `experiments/real_smolvla/validate_ledger.py` at
  the same upstream commit. It preserves strict array hashes, complete v3
  contract checks, producer/environment action agreement, same-condition
  replay checks, and initial-state-only paired comparisons. NumPy is lazy and
  optional until hashed array records are validated.
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
- RoboPAD campaign resource limits: the existing `ResourceBudget` and frozen
  campaign compiler now carry the source campaign manifest's GPU-hour, output
  byte, policy-query, retry, and per-cell timeout ceilings. The shared runner
  audits those measurements without introducing a second campaign ledger; the
  source basis is `experiments/outcome_campaign.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`, source digest
  `d19822c6928fb374359a0abdf5d72749aa4fec9cb8c29d068be7689933953c12`.
- RoboPAD conservative outcome analysis: `benchstudio.analysis.outcome_report`
  is a direct port of `experiments/outcome_report.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `687f8ed573248651c25fcf45616804d6fad5cfbecb0000b4dbd0cb4a62e760bf` and
  source-test digest
  `6f043ddfe0c4f43a4df3f07aa031dbcf419a4d877e045b8d4bab6883b335b943`.
  The port preserves frozen task/seed/parent panels, conservative missing-cell
  bounds, exact discordance intervals, and explicit attempted/complete/missing
  accounting; training and official outcome authority remain external.
- RoboPAD deterministic outcome exposure scheduling:
  `benchstudio.campaigns.outcome_schedule` is a direct port of
  `experiments/outcome_schedule.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `36dfa5060d0cb0161b09f02c43954300a237f0a5898ab91342ad6e7e23e1ec9b` and
  source-test digest
  `d6a6b5eeff857741f9cd45893545403c48cd8796b25dde500b6ac382b4e9cd47`.
  The port preserves deterministic hierarchical sampling, S/M/U/C exposure
  identity, mask validation, atomic JSON round-trips, and schedule hashing.
- RoboPAD evaluation-branch integrity: `benchstudio.analysis.outcome_eval` is a
  direct port of `experiments/outcome_eval.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `a630bdec6559a86fae0f8a7c1c13619c9a4398d0249bc2201ddde7fd0972ce5e` and
  source-test digest
  `abf10ecf2733aad3167e9a2b0d6d642a469c5f3d52f03f45b719d48e0517a280`.
  The port preserves arm prompt roles, pre-policy/contact exclusions, first
  attainment semantics, and independent replay checks for evaluation branches.
- RoboPAD outcome metadata and prompt conditioning:
  `benchstudio.analysis.metadata_conditioning` and
  `benchstudio.analysis.outcome_prompt` are direct ports of
  `experiments/metadata_conditioning.py` and `experiments/outcome_prompt.py`
  at upstream commit `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source
  digests are `be0e7d9c3587893e548ae0ba57309e47ebbf3f3c0fd2e80eeb85181afc8bdef2`
  and `d24bd9658f942484f0bc6c7ec96a87c8bb14a643a9fe2ca2b3043b96b3e27066`,
  with source-test digests `a0386fd0c2d7fe815c02408d94430ccda4dcc15317ec0e9be8a4f27885d0b296`
  and `d48e92e163d3ae26a7cf768f475e76c3d40bc0c6aa3240e383bb0b840ed83deb`.
  The ports preserve bounded metadata vocabularies, explicit unknown labels,
  training-versus-inference prompt separation, and desired-success semantics.
- RoboPAD development-only receipt safeguards:
  `benchstudio.analysis.development_receipts` is a direct port of
  `experiments/outcome_development.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `8d7bd15c273684bd992d57141d6ac880f5d169655103c57429455ecf44a06fd3` and
  source-test digest
  `4199155ff47a1a2854a366e1b577ed870709190b8447595595f569fe8c3e6716`.
  The port preserves fail-closed development-only/science-ineligible flags,
  zero/one-update checks, digest identities, and atomic receipt publication.
- RoboPAD hashed dataset-manifest resolution: `benchstudio.analysis.
  dataset_manifest` is a direct port of `experiments/outcome_dataset.py` at
  upstream commit `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `05bc2d9e274050c2fe137573ec04a4c0acbeebd1a31e9978e15d3791d0cebad9` and
  source-test digest
  `88b46d96127a3cdda98ce36ba25b05bc6e1ecbe6b47efd06458df209f9006bc1`.
  The port preserves path containment, SHA-256 binding for observations,
  actions, and outcome evidence, fixed 50-action windows, split/lineage
  checks, and explicit unknown-outcome exclusions.
- AlpaBridge: `benchstudio.integrations.alpasim_metrics` is a direct
  dependency-free port of `src/alpabridge/neutral/alpasim_metrics.py` from
  upstream commit `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`. Its source digest
  is `4e55083695485f7405f1bc6992699b16a747665513bd24036ddd29e67acc182c`.
  The port retains the original text/JSON/CSV loaders, metric aliases,
  threshold gates, run-count accounting, and explicit distinction between
  sensor-realistic evidence and official policy benchmark scores. It does not
  import AlpaSim or claim official scoring authority.
- AlpaBridge lifecycle: `benchstudio.integrations.alpabridge_lifecycle` is a
  direct port of `src/alpabridge/simulator/lifecycle_service.py` from upstream
  commit `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`, source digest
  `cd380c740ef5957d3f980188a3b726c33504cf1662c566684cf30bbf06f9cf24`.
  The port preserves structured lifecycle events, hardened late-message
  handling, cleanup/isolation behavior, and strict-mode failure evidence.
- AlpaBridge camera calibration: `benchstudio.integrations.
  alpabridge_camera_calibration` is a direct port of
  `src/alpabridge/driver/camera_calibration.py` at upstream commit
  `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`; source digest
  `f2ecef4834502681f0daa1f17b39acda238fd0a506f7f878a073080a077ea434`.
  The port preserves oneof model selection, native-resolution validation,
  per-axis scaling of pixel intrinsics to delivered frames, raw camera-proto
  retention, and graceful handling of incomplete rigs. AlpaSim protobufs and
  driver serving remain external.
- AlpaBridge policy registry: `benchstudio.integrations.alpabridge_policy_registry`
  ports the reusable registry/precondition/configuration core from
  `src/alpabridge/driver/policy_registry.py` at commit
  `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`; source digest
  `b4c4fb44bf95e296363866aec2f19ea096b817f837dd423ed7a39651108780da`.
  AlpaSim-specific factories remain injected by the owning runtime.
- AlpaBridge telemetry production: `AlpaBridgeTelemetryWriter` in
  `benchstudio.integrations.alpabridge` ports the dependency-free writer and
  summary behavior from `src/alpabridge/driver/driver_service.py` at upstream
  commit `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`; source digest
  `d8db8d0dc6a296edcd7e52793b3b03da60414457b416a2cc3829926db1d81b6f`.
  The AlpaSim gRPC driver and model execution remain external.
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
- URDF Studio / `urdf-ops` replay timing: `benchstudio.integrations.
  teleop_replay_timing` extracts the source service's timestamp selection,
  monotonic schedule construction, logical clock, and wall-clock clock. The
  source file is `backend/services/teleop_replay.py` at commit
  `561dc335cc7808f62d098dbaf7e05111ae444b28`, digest
  `bdc27b654f8dd12c27f81e4b3e0ce898408b623bcc9ef129f4e4f8502b212190`.
  Gateway execution and robot-state validation remain external to this core.
- URDF Studio / `urdf-ops` world bridge: `benchstudio.integrations.
  urdf_world_bridge` extracts the dependency-free wire contract from
  `backend/world_bridge/types.py`, `event_codec.py`, and `worldd_client.py`
  at upstream commit `561dc335cc7808f62d098dbaf7e05111ae444b28`. Source
  digests are `57c4905fa1566b11f0c897024434d32c88d8d078dc5deb6357a5d4edc946983e`,
  `f4337e47297cf91fc4225c13efd69acf07bee7a2d95ee0b3dcef0e8964eaa6a4`, and
  `b8a85317ee4656481a378e10a0f4decb3d63e58d08b44fe34321d19847475ddb`.
  It preserves event/transition mappings, strict wire parsing, timestamp
  conversion, finite joint-state validation, and command acknowledgment
  semantics; the Pydantic service and robot authority remain external.
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
