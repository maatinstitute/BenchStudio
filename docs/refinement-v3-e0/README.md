# E0: exact model-free fixture (DRAFT, NOT AUTHORISED, NOT RUN)

E0 is a **non-counting** plumbing run of the Protocol E harness on the π0.5 stack. It is a **proposed addendum to `13_EVALUATOR_VALIDATION.md`**: it does not edit that file, but it adds three rules that only Alba can approve:

1. **A non-counting execution class.** E0 runs under its own scope (`PROTOCOL_E0_PI05`) and document (this file). It never yields an evaluator verdict, and its outcome is not counted under `13` E6. The counted run in `13` E7 is unchanged and still needs its own `PROTOCOL_E_PI05` authorisation.
2. **ISO for E0 only.** `13` E6 makes ISO mandatory against the two confirmation manifests. E0 instead relies on official-state disjointness by construction, plus a planted-collision control (NC2).
3. **Single use and change control.** The first E0 execution under an authorisation consumes it, enforced by a ledger marker written before any native import. If E0 fails, any change to the harness or fixtures goes back to Alba before the counted run. The counted run's spatial GOAL_UNMET/HORIZON fixtures are fixed by `13` E3 (task 0, scripted no-op), so E0 leaves nothing to select.

Kept apart from the counted run by construction:
- its own program, `protocol_e0.py` (this directory);
- its own scope and document;
- the authorisation is single-use;
- every output file is wrapped `{"non_counting": true, "scope": "PROTOCOL_E0_PI05", ...}` with `.e0trace.json` / `.e0samples.json` suffixes;
- no export path to BenchStudio;
- the program's best result is `E0_PLUMBING_PASS_NC1_PENDING`.

The authorisation binds the whole gate chain: `evaluator_validation.py`, `release.py`, `v3common.py`, `client_openpi.py`, `common.py`, `launch_guard.py`, `protocol_e0.py` and the fixture file. The counted harness itself is called unchanged.

## Verified inputs

"Verified" means read from the pinned source named in the row, read-only. "Host" means it can only be read on the RTX host before the run, and is not invented here.

| Item | Value | Source / status |
|---|---|---|
| OpenPI revision | `215abfb217dbac7d5f1273282331b9b1866c0479` | `experiments/protocols/v3_qualification/pi05.json:72` (PR #5) |
| LIBERO revision (OpenPI submodule) | `f78abd68ee283de9f9be3c8f7e2a9ad60246e95c` | OpenPI @215abfb `third_party/libero` gitlink, read via GitHub API. **Enforced on host:** `protocol_e0.py` runs `git rev-parse HEAD` in the imported LIBERO tree and refuses any other commit |
| Benchmark / suite | `benchmark.get_benchmark_dict()["libero_spatial"]()`, default `task_order_index=0` → order `[0..9]` (identity) | LIBERO @f78abd6 `libero/libero/benchmark/__init__.py:83-121` |
| Task 0 | `pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate` | LIBERO @f78abd6 `libero_suite_task_map.py`, `libero_spatial[0]` |
| BDDL | `bddl_files/libero_spatial/<task>.bddl`, sha256 `9b59eb1287802868ad9bc78d58e6d36d4ba31134e679cfdbdf4b0feb660c959b` | LIBERO @f78abd6. Byte-identical to the hf-libero 0.1.4 copy |
| Goal | `(And (On akita_black_bowl_1 plate_1))` → atoms `[["on","akita_black_bowl_1","plate_1"]]` | BDDL line 131-133. Harness parser output (offline) |
| Reset-state source | `suite.get_task_init_states(0)[0]`, loaded by `torch.load` from `init_files/libero_spatial/<task>.pruned_init` | LIBERO @f78abd6 `benchmark/__init__.py:158-165` |
| Init-state file | `<task>.pruned_init`: 44,271 bytes, sha256 `cbbc73792ce546c9bec181fd328a411d3183074840b282671dee481511381d0a`, git blob `543deb5f5c1d2ca29426a7b77964c9273f71197d` | LIBERO @f78abd6 via GitHub API. **Enforced on host:** the program hashes the file it loads and refuses a mismatch. The sha256 of state row 0 (`np.asarray(state).tobytes()`) is computed on the host and recorded; it is not known offline |
| Env | `OffScreenRenderEnv(bddl_file_name=<BDDL>, camera_heights=256, camera_widths=256)`, `env.seed(7)` | `client_openpi.py:32,53-59` (frozen v2 client, called by the harness) |
| Settling | `env.reset()`; `env.set_init_state(state)`; 10 × `DUMMY_ACTION` | `client_openpi.py:31-32`; `evaluator_validation.run_fixture_pi05` |
| Action | `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0]`: 7 dims, gripper −1, identical to `DUMMY_ACTION` | `evaluator_validation.NOOP`; `client_openpi.DUMMY_ACTION` |
| Steps, F1 GOAL_UNMET | 20 actions after settling | `evaluator_validation.GOAL_UNMET_STEPS` |
| Steps, F2 HORIZON | 220 actions after settling (`MAX_STEPS["libero_spatial"]`) | `client_openpi.py:33` |
| `done` | `done = self._check_success()` after every step; `_check_success` = conjunction of `parsed_problem["goal_state"]` predicates | LIBERO @f78abd6 `bddl_base_domain.py:800-809`, `problems/libero_tabletop_manipulation.py:135-143`. This is the G11 source read; **host** re-read still owed |
| Termination | the env never ends by itself within 220 steps (robosuite horizon 1000, `bddl_base_domain.py:64`). The harness loop stops on `done` or at 220 | as above |
| Renderer | `MUJOCO_GL=osmesa` (set by `protocol_e0.py` if unset); RTX 5090 WSL (D4) | the record holds `MUJOCO_GL`, platform, Python, executable, robosuite/mujoco/numpy versions, LIBERO root and revision, init-file hash. **GL renderer strings are not captured**: the harness driver creates and closes the env internally |
| Fixture file | `e0_fixtures_pi05.json` (this directory), sha256 `c8288b698466a5e67722894bc91535c80586875e6d787eb348335c8ae8cd9657` | this package |
| Harness | `evaluator_validation.py` sha256 `bd06a675144e…` (PR #5 @3b4a78e), unchanged | |

## Predicted outputs

| | F1 `E0_pi05_spatial_t0_unmet` | F2 `E0_pi05_spatial_t0_horizon` |
|---|---|---|
| trace rows | 20 | 220 |
| `done` / independent goal | false / false at every step | false / false at every step |
| `compare().agrees` | true | true |
| distinct per-step state hashes (NC4, "state advances") | ≥ 2 | ≥ 2 |

Every expected outcome is "false", and a harness that read nothing would also produce false. The agreement adds little. E0's weight rests on NC2, NC1 and the environment record. NC4 is weak (below).

## Controls

| # | Detects | Implemented as | Pass condition |
|---|---|---|---|
| NC1 | E-AUTH inert | operator runs `protocol_e0.py` three times before the real run: (a) no authorisation, (b) a `PROTOCOL_E_PI05`-scoped authorisation, (c) one bound to `13_EVALUATOR_VALIDATION.md`. The transcripts are kept. Tested offline with the driver stubbed | each REFUSED, exit 2, with no ledger marker, output directory or native import |
| NC2 | ISO collision branch inert | the program plants the official state's own hash (same expression as the harness) and runs F1. It counts only the harness's exact message | `EvaluatorIncident("fixture state collides with a confirmation state")` before stepping |
| NC3 | partial evidence reaching BenchStudio | structural: no export call in `protocol_e0.py`; outputs are wrapped and tagged non-counting, so they are not in BenchStudio's sample schema. The exporter's refusal of partial sets is shown offline | n/a |
| NC4 | state not advancing | ≥ 2 distinct per-step state hashes per fixture | both true |

**What the controls do not show.**
- **NC2** shows the branch is live. It does not show that the confirmation manifests' hash convention matches; that needs the generator, which is not written.
- **NC4** is weak. The hashed vector is `sim.get_state().flatten()`, which in robosuite's binding probably includes sim time (not verified). If so, NC4 shows only that the simulator stepped, not that the goal check reads live state. Nothing in a no-op fixture can show live goal reading, because the goal never changes. That waits for a goal-reached fixture in the counted run.

## Output files (new directory; the program refuses an existing one)

- `e0_record.json`: schema `protocol_e0_record_v1`, `non_counting: true`, scope, authorisation digest, ledger marker, input hashes for the whole gate chain, host record, NC2, NC4, results, verdict.
- For each fixture, `*.e0trace.json` and `*.e0samples.json`, each wrapped and tagged non-counting.
- The ledger marker `<authorisation sha256>.e0_started` is written in the ledger directory.
- The NC1 transcripts are saved beside the output by the operator.

## Verdict (E0 only)

- **Program result `E0_PLUMBING_PASS_NC1_PENDING`:** host checks passed, NC2 fired with the exact message, both fixtures `agrees`, and NC4 holds.
- **E0 PASS (reviewer's verdict):** the program result above **and** the three NC1 transcripts show refusals. The program cannot certify NC1 itself.
- **E0_FAIL:** a host check failed, NC2 did not fire (or fired with another message), a disagreement occurred, NC4 failed, or a harness incident or fixture error occurred. Investigated before anything changes, and any change goes back to Alba before the counted run.
- **UNINTERPRETABLE:** any other exception, such as an import or env build failure.
- A second execution under the same authorisation is refused. A new authorisation is required.

E0 PASS licenses only: "on this host and stack, the harness builds the env, steps it, writes the record, and its authorisation and ISO branches refuse". It is not evaluator qualification. It says nothing about `done` on goal reach, nor that the goal check reads live state.

## Still needed before E0 can run

1. Alba's decision on the three addendum rules at the top of this file.
2. Her authorisation file for `PROTOCOL_E0_PI05`, bound to this document's sha256 and to the eight files listed above.
3. A host session on the RTX 5090 (WSL, OSMesa). The pinned host checks run inside the program.

## Offline checks

`e0_offline_checks.py` exercises the gates and verdicts with the native driver and host checks stubbed (8 checks; 8/8 on Python 3.12 and 3.8.20 against PR #5 @ `3b4a78e`). No offline check can reach the real `run_fixture_pi05`, which imports LIBERO before its ISO check. The driver path is exercised only by a host run.
