# Source attribution

- `benchstudio.analysis.alpabridge_review` is a direct dependency-free port of
  `alpabridge.audit.review` from the AlpaBridge research repository. It
  preserves the upstream severity profiles, intervention classification,
  frame bookmarks, paired bookmarks, and critical-event context bundles;
  optional Rerun visualization and audit-log export remain external. The
  source digest is `ede906c260529bede52e395ecffac4d01009b45de8b0cee0766f0ef494e3049b`
  and the upstream review-test digest is
  `86a50a99fcff62d47f6084ea6927934d71c11906e75882f6106002ff42baa6b6`.
- `benchstudio.integrations.alpabridge_signal` ports the dependency-light
  route-waypoint, structured-hazard, visibility-risk, dynamics-risk, and
  usable-route normalization boundary from
  `src/alpabridge/simulator/alpasim_signal.py`. The AlpaSim Scenario model,
  serving runtime, and physics authority remain external. Source digest:
  `3a18ae0293f8c9aa738a787f17fb9b0ba363833c790e61ec9fa1503ec6f04838`.
- `benchstudio.scenarios.world_scene_package` ports the URDF Studio
  `WorldScenePackage` manifest, digest, validation, and file-backed version
  registry boundary from `backend/models/world_scene_package.py` and
  `backend/services/world_registry.py`. It preserves runtime targets,
  interface/snapshot limits, finite joint-state checks, version uniqueness,
  canonical manifest digests, and atomic registry replacement while leaving
  Pydantic service models and simulator execution external. Source digests:
  `f502d0a6ff8f321719cf6a05852ff331cbcae3612b69ed641c1e78675b2e2e63`,
  `d17dc8511e758bdc58e4ec3d8c978459f1c040a2936b6c483e5111414ce51a65`, and
  `1d9cf5c2604409dc90ba231eb7d65f87a5edd76c914b938bf4c1587acf9683a5`.
  Registry listing also preserves latest-version selection, owner/tag/query
  filtering, runtime-target summaries, and metadata trust-level derivation.
- `benchstudio.scenarios.world_rollout` ports the dependency-free URDF Studio
  rollout campaign/checker-profile, artifact-digest, bounded NDJSON trace and
  decision import, and decision-counting boundary from
  `backend/models/world_rollouts.py` and `backend/services/world_rollouts.py`.
  The external rollout CLI, worker queue, and simulator execution remain
  external. Source digests:
  `c1d2329aa26353ce9f3bc0b6495a76f93539bf90d37d5e1308f43e474a737b7f`,
  `634985720723ecba023fbc48b99186a0c6d55f90cbbfe5cd791e5212d74e2407`, and
  `71da3c8737d37bd2e116c9647c2a172dfb32dca32c05272dec2fa4c14aa0db91`.

BenchStudio uses source-backed adapters and explicit independent boundaries for
the following projects. Product runtimes are not vendored into this repository.

The AlpaBridge source revision used by the ports is retained in
`docs/source-snapshots/alpabridge-27c96e6.json`. The local source repository
verifies commit `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2` and tree
`0d72a01dfe45b12182e16338603923dd87891d3e`; the current public remote branch
does not expose that historical commit, so the snapshot manifest is the
authoritative provenance record rather than an unresolved GitHub URL.

The ordinary `CampaignExecutor` consumes an optional frozen
`protocol.worldepisode` binding and runs the source-backed preflight before
scheduling attempts; the executor owns scheduling while WorldEpisode remains
the canonical semantic validator.

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
  `load_refinement_source_plan()` and `compile_refinement_source_plan()` also
  import an existing upstream JSON plan without regenerating or reordering its
  rows; the imported BenchStudio plan records both the source-file and source-
  schedule digests.
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
  balanced schedule-selection, and parity-report functions from
  `experiments/tooling/run_paired.py` at
  upstream commit `8c92e66c7ab19403822cb87908253260666fb3a6`; source digest
  `09fbef924edbf075ea245db6d59ba4e181785e0d3a2f66d632f264d82970458f` and
  source-test digest
  `256e0e6ebbe34f5930ba1afb8d1d9b153ee84bd3d00bb5b4dd0a80e9d1562313`.
  The port preserves the upstream fail-closed condition-block, schedule-digest,
  task/state/seed-balance, and complete-pair selection checks. CUDA/LeRobot
  rollout execution and checkpoint ownership remain external.
- Refinement/Refresh development gates: `benchstudio.analysis.
  refinement_protocol` also ports the dependency-free `compare_arrays`,
  `image_variants`, and code-identity `profiler_counts` gates from
  `experiments/tooling/development_gates.py` at the same upstream commit;
  the CUDA model and simulator execution surrounding those gates remains
  external.
- Refinement/Refresh result analysis: `benchstudio.analysis.result_metrics`
  is a direct port of `experiments/real_smolvla/result_metrics.py` from the
  same upstream commit. The source digest is
  `1b493b3643c89831757f7a3a5c75632b43512390d8eac12e6b1ce4960756d867`, and
  its regression-test digest is
  `f5fa8606d93263f5af0bd8799c640b62c83c2b139ea68da2598d227d96e06698`.
  The port preserves completed-outcome reconciliation, task/group identity
  checks, ledger-version timing provenance, and control-to-neural accounting.
- Refinement/Refresh archived deployment evidence: `benchstudio.analysis.
  smolvla_deployment` validates the retained `real_smolvla/manifest.json` and
  `results/summary.json` evidence boundary using the same pinned checkpoint,
  LeRobot revision, control/neural accounting, and timing limitations declared
  by the upstream archive. It records the input-file digests, but does not copy
  model weights, load LeRobot, infer pairing, or claim a new live execution.
- Refinement/Refresh ledger verification: `benchstudio.analysis.ledger_validation`
  is a source-backed port of `experiments/real_smolvla/validate_ledger.py` at
  the same upstream commit. It preserves strict array hashes, complete v3
  contract checks, producer/environment action agreement, same-condition
  replay checks, and initial-state-only paired comparisons. NumPy is lazy and
  optional until hashed array records are validated.
- Refinement/Refresh query recovery: `benchstudio.analysis.refinement_query_recovery`
  ports the dependency-free direct-record query recovery boundary from
  `experiments/tooling/analyze_execution.py` at the same upstream commit;
  source digest `5dddcedec6bc6ef76dd207759cdb951afc0ec4d5bdce15be8811ad18f29634ea`
  and source-test digest
  `9582bce0d57d499f47a65ee48d79648ca5ced6d98ca318fad2c8762f8383c800`.
  It preserves the fixed query/projection protocol, all-attempt wall-time
  denominator, explicit zero-success undefined status, and unknown-field
  behavior. Full rollout reconciliation and model execution remain external.
- Refinement/Refresh rollout manifest audit: `benchstudio.analysis.
  refinement_rollout_audit` ports the dependency-free `episode_key` and
  `reconcile_rollout_manifest` boundary from the same
  `experiments/tooling/analyze_execution.py` source and test digests above.
  The port preserves declared-population binding, schedule/runtime digests,
  paired-cell completeness, completion totals, and aggregate-success checks;
  action-journal reconciliation and rollout execution remain external.
- Refinement/Refresh rollout journal audit: `benchstudio.analysis.
  refinement_rollout_audit` also ports `check_initial_state` and
  `reconcile_rollout_journal` from the same source boundary. It preserves
  content-addressed numeric states, keyed noise/generation cadence,
  producer-to-environment action binding, terminal flags, termination reasons,
  and completion records; simulator execution remains external.
- Refinement/Refresh microbenchmark validation: `benchstudio.analysis.
  refinement_microbenchmark` ports `validate_microbenchmark` from
  `experiments/tooling/analyze_execution.py` at the same upstream commit;
  source digest `5dddcedec6bc6ef76dd207759cdb951afc0ec4d5bdce15be8811ad18f29634ea`
  and source-test digest
  `9582bce0d57d499f47a65ee48d79648ca5ced6d98ca318fad2c8762f8383c800`.
  It preserves declared allocation, paired on/off action and timing hashes,
  shared-noise keys, instrumentation hook counts, action-artifact identity,
  and measurement-only output selection; model execution remains external.
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
- RoboPAD path geometry: `benchstudio.conformance.path_geometry` ports the
  conservative swept-box segment/slab screen from
  `experiments/icra_path_geometry.py` and its proper-rotation validation
  boundary from `experiments/icra_reference_pose.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digests are
  `1beec4f1e9c87fbcb6a1e5bb5e0b48c88b69ef7a217f4b63605be90cb0f4e606` and
  `1a281a6b43c32e3e8c79ac57eb28f765e1677a0e7e1b646c909cc139a9d17c79`.
  The port is an intervention preflight only; full robot geometry, tracking
  error, and physical safety remain external.
- RoboPAD fixed reference controller: `benchstudio.integrations.FixedReference`
  is a source-backed port of `experiments/icra_reference.py` at the same
  upstream commit. Source digest is
  `3ed7717336846e0ef18841f7193984d0d095d9b55016f23a0568f0f8b68d5f84`, and
  the upstream test digest is
  `106d94c558db3f5f67f0d0f6b719a764202564b7d4e43a5a090ef6d2bbd0980f`.
  The fixed horizon, source-held conditioning, action clipping, and defensive
  copy semantics are preserved; waypoint derivation and execution authority
  remain external.
- RoboPAD competence evidence: `benchstudio.integrations.robopad_competence`
  ports the dependency-light persistence, termination, exact replay comparison,
  stale-goal rotation guard, and compact-record helpers from
  `experiments/icra_reference_competence.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`. Source digest is
  `4d2223b22f8384629e7e51cd8f68f7e242775e831d5f686630c573ee63dea83c`, and
  the upstream test digest is
  `bce4cd71464e83feed06807825cd015ff3cc7c29e235cc34420cb2f12c60fc73`.
  The port preserves bounded evidence writes and exact replay semantics;
  physical rollout execution and source geometry remain external.
- RoboPAD source geometry adapter: `benchstudio.integrations.
  robopad_reference_adapter` ports the read-only geometry extraction,
  transformed grasp transfer, conservative goal construction, and frozen
  stage-goal mapping from `experiments/icra_reference_adapter.py` at upstream
  commit `4ecd468cc67cc40681ca2af9097b7ade5825fadd`. Source digest is
  `9a7e87062fc6450f00a0d55daa309edfcf7af396729d73fa3575e1eb679bf4f3`, and
  the upstream test digest is
  `deb6c852547c567a5d7950f1021ab5be03f9121b93394d39a6033b90106bd1ce`.
  The adapter remains read-only and records unresolved live-geometry and
  controller checks instead of claiming competence.
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
  `tests/test_outcome_schedule.py::test_robopad_source_golden_vector_is_byte_identical`
  locks a source-generated seed-123 schedule digest and first exposure vector
  so the port's serialized behavior remains parity-tested against RoboPAD.
- RoboPAD outcome-plan verification: `benchstudio.campaigns.load_outcome_plan`
  and `verify_outcome_plan` consume the source-backed
  `smolvla_outcome_plan_v1` preflight artifact, preserving its payload digest,
  training/evaluation cell identities, reserved continuation counts, and
  policy-query denominators. This is an evidence/preflight boundary only;
  training, checkpoint, simulator, and official outcome authority remain
  external.
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
- AlpaBridge route geometry: `route_arc_length_m` in
  `benchstudio.integrations.alpabridge` is the dependency-free route-extent
  extraction from `src/alpabridge/driver/driver_service.py` at the same
  upstream commit; source-test digest
  `58367c9cd0eebf40ad77c826b56c4a3306ace532e5ee6f2dc254c0f9f84c016e`.
  The full driver-service digest above remains authoritative.
- AlpaBridge route-follower geometry: `benchstudio.integrations.alpabridge_route`
  ports the dependency-free speed-ramp, per-scene target scaling, no-braking
  guard, route sampling, straight-trajectory, clamped segment-distance, and
  nearest-polyline helpers from
  `src/alpabridge/simulator/baseline_drivers.py` at upstream commit
  `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`. Source digest is
  `6e2fca16528f78758b4af6ed62fee672ffbf880e7731253335488d37276d0250`, and
  the upstream ramp-test digest is
  `c1cf7a0c13d190806de2c80e879279d22c28a9a77f0c46eb3135f521ec83a42c`.
  The ramp remains disabled by default to preserve historical constant-speed
  samples; AlpaSim serving and driver authority remain external.
- The same route module ports `segment_point_distance` from
  `src/alpabridge/simulator/environment.py` and `_distance_to_polyline` from
  `src/alpabridge/simulator/mpc_planner.py` at the same upstream commit.
  Source digests are
  `1cb8028276ca34d7bee2f8e4b1787fad282ce7250ff776eca47554d81300d6c6` and
  `bf67ad43c767bf81d3f07e45af1a3e7990b48d925cd776195311573043a3621d`;
  their conformance-test digest is
  `4a5003fe9f5b9c53371192f8451338a64174d0585942a9d2930a46e38bc7d589`.
- AlpaBridge trajectory selection: `benchstudio.integrations.
  alpabridge_trajectory_selector` ports the speed-scaled 3-second/5-second
  reference-region scoring and candidate selection from
  `src/alpabridge/simulator/trajectory_selector.py` at the same upstream
  commit. Source digest is
  `5dfe55ef11fda051170b1b1753f262d439ab45e940d7bea679c80c0054228b50`, and
  the upstream selector/maneuver regression-test digest is
  `c80281fd146ace1a3c57141c2473d7c93569b846ec5f14eb2e5459bd99d980e6`.
  The simulator-backed maneuver generation and execution authority remain
  external.
- AlpaBridge camera-frame preparation: `benchstudio.integrations.alpabridge_image`
  ports the cover-resize/center-crop utility from
  `src/alpabridge/simulator/image_ops.py` and the fail-soft optional
  rectification boundary from `src/alpabridge/simulator/camera_rectification.py`
  at upstream commit `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`. Source
  digests are `9004d96f5d9a8db9962195535aa42a3afbd411111457a73945f6bd702d401a34`
  and `d28b7e7c640f96193bbc5a2f3bf00e9f50ac8eb2cf5b924c64095ef9c92c96a0`;
  source-test digests are `5a9dabca2690acaab75f36be5717d6d0638e100ec747541490a963ae12fe8cf7`
  and `a7faa208c70bdfd414c496a16322c277627f54bf8fae5ff07a7610b13628a891`.
  The external f-theta transform remains optional and is never vendored here.
- AlpaBridge pose-reanchored inference cache: `benchstudio.integrations.
  alpabridge_inference_cache` ports
  `src/alpabridge/simulator/inference_rate_cache.py` at upstream commit
  `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`; source digest
  `ce5a75b469d7c12c35ea6d434ea78f1ea6d4b885b552cb11abd24fa91455d94b` and
  source-test digest
  `80f4e0023362009dd61486282127de7cf2c49a117e9ead664eb863ebb093ff5c`.
  The port preserves cadence throttling, per-session isolation, world-frame
  trajectory re-anchoring, quaternion yaw extraction, and explicit cache
  eviction; policy inference and vehicle authority remain external.
- AlpaBridge/AlpaSim prediction contract: `benchstudio.integrations.
  alpabridge_contract` extracts the dependency-light prediction-shape,
  trajectory-resampling, pose-history, camera-fingerprint, and corrected-speed
  boundaries from `src/alpabridge/simulator/alpasim_contract.py` at upstream
  commit `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`; source digest
  `a9c2e2cdd31d680f5d67f7512e45f14b3b95e81285c00adbe0570069126f461f` and
  source-test digest
  `b6f73a542393192bff1ca83eae879801a18adc5cb317e90d38e7be5102b64af3`.
  The port preserves current candidate tensor shapes and selected-candidate
  access, explicit timestamp interpolation, finite-difference speed fallback,
  and deterministic image fingerprints; AlpaSim runtime and physics remain
  external.
- The same contract module ports the stateful `SensorFreshnessGuard` boundary
  from `alpasim_contract.py`, preserving session reset, pose/camera lag checks,
  timestamp advancement, frozen-image detection, and structured diagnostics.
  Its source/test provenance is the same pair recorded above.
- SmolVLA driving contract: `benchstudio.integrations.
  smolvla_driving_contract` ports
  `src/alpabridge/simulator/smolvla_driving_contract.py` at upstream commit
  `27c96e6118a6d0137fe9b1774f227b07ef3d9aa2`; source digest
  `e97d1a5608e9e3f7ab90724b6f79e8fff82f17953eef85d9aca1e15ef75d27f6` and
  source-test digest
  `62de11f3823ceaac817a1aef1b7ead7c512e1cc44ce0a8e62ae5895bb00c6d3f`.
  It preserves the four-camera provenance manifest, ego-frame trajectory-only
  output boundary, monotonic timestamps, and rejection of result-derived
  inference signals; SmolVLA weights and serving remain external.
- The same AlpaSim contract also preserves scene/session/seed runtime metadata
  and timestamp-sorted pose history for downstream evidence binding.
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
- RoboPAD bounded child supervision: `benchstudio.integrations.robopad_supervisor`
  is a direct source-backed port of `experiments/icra_assay_supervisor.py` at
  upstream commit `4ecd468cc67cc40681ca2af9097b7ade5825fadd`. The source digest
  is `658e2e73f04651178056a18a775fcac333da3ed114715d858338508b6263ddd2`, and
  the upstream behavioral-test digest is
  `6ed179fde551088517d3e46e530dd1cdfbd78b5ae8b71a34a78d9818b9b5a382`.
  The port preserves owned process-group cleanup, bounded merged logs,
  timeout escalation, exclusive attempted-run logs, reviewed parent envelopes,
  and atomic bounded receipts. It deliberately does not import RoboPAD's
  campaign manifest, child runtime, or claims authority.
- RoboPAD fixed assay allocation and source cache: `benchstudio.campaigns.
  robopad_assay_plan` directly ports `experiments/icra_assay_plan.py` at
  upstream commit `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `d4683e2f81e1ac0f332fb3c92c6d06ac39128f3242a5443107e14926d61c565f` and
  source-test digest `743a2649bcf5a3a3cdf31df32d1385c4eb4268228c5208f35b4b50873c0e253f`.
  `benchstudio.integrations.robopad_reference_cache` ports
  `experiments/icra_reference_cache.py`; source digest
  `6cdc72219d25b9a0c08ec2bc8ba0d9f39fc2acb34b640b4fc42b77a3054d2939` and
  source-test digest `d0c7b5a183abec174cc745d8bca531992b79755c44a2df85d5faec5e3a31b83f`.
  These ports preserve the 360-slot fixed design, consumed-slot exclusion,
  deterministic suffix seeds, source-attempt hash binding, no-padding
  semantics, held-source selection, and immutable retained actions; NumPy
  trace decoding remains lazy and physical/source authority remains external.
- RoboPAD paired missing-outcome bounds: `robopad_paired_bounds` in
  `benchstudio.analysis.missingness` directly ports
  `experiments/icra_missing_outcomes.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `3ea733beb3193eaa0b8ea936214583731355f9a0ad274efbb55560ef141a8a78` and
  source-test digest `be926548e7e0e856c1ed722bcf05e6b02422e9ccb08bf3a65f6689fc8f99df9c`.
  It preserves fixed denominators, binary-completion bounds, explicit unknown
  arms, and the absence of sampling-uncertainty claims.
- RoboPAD exposure quarantine: `benchstudio.analysis.robopad_exposure` ports
  the family identity and split-audit boundary from `experiments/icra_exposure.py`
  at the same upstream commit; source digest
  `2bdea057d0c14679c9013a445ffa3dad7d2296f3ed0e55d6c300e2e7865ae1ce` and
  source-test digest `3c3d76ce31057826752027e824b0e0701e1af7506b7dfac10dc649f8dd0a6362`.
  The audit remains explicitly provisional and freshness-ineligible; dataset
  bytes, aliases, and broader parent coverage are not certified.
- RoboPAD reference batch controls: `benchstudio.campaigns.
  robopad_reference_batch` ports the reservation, staged-input verification,
  and sequential no-retry dispatch boundary from
  `experiments/icra_reference_batch.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `d4cc890351ad5cbe2d99a8d4c712aacff279bcfd5422efc1d8133a7f97e7da0d` and
  source-test digest `1a7b33ea4c43c0ca9cab8f64bb552fabc18552802c70a3cdee32994494a3ecbc`.
  It preserves all-existing preflight, immutable partial claims, staged hash
  ceilings, terminal child accounting, wall-time admission, and stop-on-failure;
  it does not launch RoboPAD runtimes or claim scientific validity.
- RoboPAD evidence codec/store: `benchstudio.integrations.
  robopad_evidence_codec` directly ports `experiments/icra_evidence_codec.py`
  at upstream commit `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `48c32db3190667ffd3dbcc0ad900672fe5e6b79c7cabb8f32ac8859a79c52d19` and
  source-test digest `9b1681db4550062ab24ba5ca8599b3c247a59c7c02aa7811272acdf994e17bd6`.
  `benchstudio.integrations.robopad_evidence_store` ports
  `experiments/icra_evidence_store.py`; source digest
  `405602183782f8f79e5275509bb077b8d04fa339c8b6ba16b82ee99c5600449b` and
  source-test digest `ef9e9765654d4288617bb13c2580e2a9bc5ebce0142e533e4ce005d3f723d724`.
  The ports preserve temporal predecessor identity, bit-exact bounded delta
  encoding, persisted-byte rechecks, quota reserves, hard-link commit
  visibility, orphan accounting, and fail-closed no-retry state. NumPy remains
  optional until these integration boundaries are used.
- RoboPAD state-evidence serialization: `benchstudio.integrations.
  robopad_state_evidence.json_numpy` ports the dependency-light report
  serializer from `experiments/icra_state_evidence_probe.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `3b2d9f5d6372f01c093bb1dbf1a944e465f951aa2e82ddbc2a0c41af32263d8e` and
  source-test digest `d7de132f2f48a210b959f4243a4c1bc676fb4184cf11407d95d0d6a9874e4ffb`.
  It preserves explicit NumPy scalar/array JSON conversion and rejects unknown
  metadata instead of stringifying it. The simulator restoration, physics
  inspection, and no-action probe remain external.
- RoboPAD intervention preflight: `benchstudio.conformance.
  robopad_intervention` ports the fixed distractor grid from
  `experiments/icra_b_candidates.py` and the conservative support/contact
  screen from `experiments/icra_b_physics.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`. Source digests are
  `51d11a546370f70fdbeebeb40bf79231c75ea1d0eca805495ea8713c85086619` and
  `0e754cf9974bef714ad6ce4a4e09b35eb1426aac331ffe7e6a2ec104d2fe7c42`; source-test
  digests are `05472f0cc96f16e2a71de5b3bbbc06e7ae20caaa3af5ccf2551084a4634a2bb2`
  and `72d530d29964b07b5eed8c64927c770286ba824c0f5a86ec275311456b20d9b5`.
  The port preserves outcome-free state proposals, untouched-coordinate
  guarantees, support inset/penetration thresholds, and contact rejection;
  policy search, simulator restoration, and dynamic stability remain external.
- RoboPAD visual balance: `benchstudio.analysis.robopad_visual_balance` ports
  `experiments/icra_visual_balance.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `9230cd1f898dbfe7651e4c5e1d0f9e8b901da8ff826a83d55483f73838e92534` and
  source-test digest `4c160ff0a8ba80bfeaa6881bf6613532ccdda1a4f26aa70308977654c7e8fc46`.
  It preserves signed RGB/floating image distance, per-camera thresholds,
  stable deterministic pair selection, explicit physical-validity handling,
  and outcome-free matching. Image provenance and simulator execution remain
  caller-owned.
- RoboPAD assay reservations: `benchstudio.campaigns.robopad_assay_claims`
  directly ports `experiments/icra_assay_claims.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `36217f6f2db6e60d0ef2b2de5618f4e3917c51a6c9bcefa0b5325b3322337c51` and
  source-test digest `3c05ed16a411bf5f948e55f17e73b95e5bd089e53ea3934aa2ede7b899fd2773`.
  It preserves canonical fixed run allocation, exclusive no-retry claims,
  binding-hash receipts, no-resume start markers, canonical JSON/regular-file
  checks, and post-start tamper detection. This is reservation evidence, not
  scientific claim scoring; the latter remains in `benchstudio.analysis.claims`.
- RoboPAD restored initialization and runtime-plan contracts:
  `benchstudio.integrations.robopad_initialization` ports the reviewed
  `initialize_restored_pose` boundary from `experiments/icra_assay_initialization.py`
  at upstream commit `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `2b0b70f3b7a1a244d73e9f777e3c77a1a4f40f0f7384a5e539a71ccb20a33124` and
  source-test digest `dd713e25d4a5da821bfd8bd50e1212aacaa898c3011ac5bfd44f11f743adfba9`.
  `benchstudio.campaigns.robopad_runtime_plan` extracts the dependency-light
  fixed child-run, replay-order, allocation-manifest, and resource-limit
  contracts from `experiments/icra_assay_runtime.py`; source digest
  `421e1878d25874473cc76b5a264bf7dedc73261a0471725631ef1d20633dc791` and
  source-test digest `7566a00c11dfd4a636a0e5296424adad61f9e0ce188e6bdff3cd76cb88b79e22`.
  The ports preserve no-action initialization checks and fixed plan identity;
  simulator/runtime launch, policy execution, and physical authority remain external.
- RoboPAD cell-store runtime extension: `benchstudio.integrations.CellStore`
  ports the semantic digest, bounded auxiliary-array, partial-action-journal,
  pending-execution-unknown, and terminal-receipt portions of
  `experiments/icra_assay_runtime.py` at the same upstream commit and source
  digest `421e1878d25874473cc76b5a264bf7dedc73261a0471725631ef1d20633dc791`;
  the upstream runtime-test digest is
  `7566a00c11dfd4a636a0e5296424adad61f9e0ce188e6bdff3cd76cb88b79e22`.
  The extension reuses the ported bounded evidence store, retains partial
  failures without retry semantics, and does not launch the external runtime.
- RoboPAD rollout semantics: `benchstudio.integrations.robopad_rollout` ports
  `experiments/icra_rollout.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `6c9b6f65c8c6e13951d83d2c4c6886c72d094fc58be792a90b169ae772a4aa25` and
  source-test digest `696aa44655d4dd47766ccc9c1d2ca8c5177cda4a8de595d6bde2ad0fff69f7b1`.
  The port preserves committed-prefix execution, absolute ten-step suffix
  queries, native-success gating, explicit wall-clock/environment-terminal
  outcomes, and pending-action execution-unknown evidence; environment,
  policy, and persistence authorities remain external.
- RoboPAD remaining reference evidence: `benchstudio.integrations.robopad_remaining`
  ports the dependency-light scope, bounded persistence, scalar conversion, and
  dense/terminal frame-retention helpers from
  `experiments/icra_reference_remaining.py` at upstream commit
  `4ecd468cc67cc40681ca2af9097b7ade5825fadd`; source digest
  `69088b253df546782235f772c140f9d8b0c2490620758534531299731315a210` and
  source-test digest
  `c390738762972785707a618f4a99b9092bd05d5c5e7fce5f99d91f93ac964bcf`.
  The port preserves the fixed six-parent world scope, non-retry rule, results
  quota policy, and original/physics RGB frame names; MuJoCo/reference rollout
  execution remains external.
- URDF Studio, AlpaBridge, RoboPAD, refinement/refresh experiments, and
  `urdf-ops`: BenchStudio exposes independent contracts for scenario identity,
  lifecycle, campaign accounting, counterfactual lineage, and embodiment
  mapping. The `PolicySession` boundary is informed by AlpaBridge's session,
  modality, readiness, and latency behavior; it is a dependency-free contract,
  not a port of the AlpaBridge service. The AlpaBridge telemetry adapter reads
  the published v3 JSONL shape and preserves its latency-target, route-source,
  and model-load event semantics; it does not import or reimplement AlpaSim.
  Product-specific runtimes remain external.

The RoboChallenge observe-only adapter and
`examples/external_runtime/robochallenge_mock.py` are BenchStudio-owned
transport fixtures, not a port of the RoboChallenge client. They preserve
opaque payload bytes and protocol digests for boundary testing while leaving
execution, safety, and official scoring with the external platform.

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
