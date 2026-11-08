# AlpaBridge capability migration

Source reviewed: [AlpaBridge main at abf547b](https://github.com/amtellezfernandez/AlpaBridge/tree/abf547bbeef860d9c05e038a9cc6b84eae7e62a1),
including its README, pyproject entry points and native scene-batch runner.
This is a migration assessment, not an implemented AlpaSim backend or native test.

BenchStudio should own the common evaluation experience. AlpaBridge can become
the AlpaSim backend package rather than duplicate that experience.

| Capability | Proposed owner | Current boundary |
| --- | --- | --- |
| Python/CLI evaluation configuration, named backend discovery | BenchStudio | Implemented with offline tests |
| Bounded async execution, batch-capable runtime dispatch | BenchStudio | Implemented; independent session state remains a backend responsibility |
| Run status, retained evidence, paired comparisons and ablations | BenchStudio | Implemented generic path; native metric identity must be mapped faithfully |
| Native driver/gRPC session, AlpaSim plugins and Docker services | AlpaBridge | Preserve the existing successful path and lifecycle |
| Camera calibration/freshness, route frames and trajectory contracts | AlpaBridge backend, using shared helpers where qualified | Preserve native guards and conformance fixtures |
| Seven policies and their checkpoints/tokenizers | AlpaBridge backends | Reuse adapters; no evidence that every backend is portable to a different runtime |
| Retry/resume and per-scene accounting | Existing AlpaBridge runner until mapped and tested | Generic async failure persistence is not durable per-trial recovery or equivalent native retry semantics |
| Official scoring and source telemetry | Native evaluator/backend | Never infer success from process exit alone |

## First integration

Register an optional installed pipeline in the AlpaBridge package using
benchstudio.pipelines, following the native recipe contract. Its check() should
delegate to AlpaBridge's existing readiness controls and its run() should delegate
to the native scene-batch runner, retaining per-scene identities, telemetry,
official metric provenance and failure/retry records. Use the same BenchStudio API
and CLI; do not introduce an AlpaSim-specific launcher in BenchStudio.

The current AlpaBridge batch runner treats scenes as statistical units, checks
artifact completion, and owns Docker cleanup and retries. Preserve those semantics
until equivalent tests and authorized native traces establish replacement parity.

BenchStudio's generic engine currently retains failed-run status, not durable
per-trial partial results/recovery. That is not enough to retire AlpaBridge's batch
runner. Likewise, existing telemetry/contract helpers are not a live AlpaSim
service adapter.

Keep integration optional while BenchStudio is distributed through a private
repository. Public AlpaBridge installation must not suddenly require access to an
unavailable private package. No license or dependency change is made by this
assessment.

Native session and scoring parity, representative throughput, and lifecycle
failure tests are required before replacing the existing native control path.
No simulator, GPU or driving-policy execution was performed for this review.
