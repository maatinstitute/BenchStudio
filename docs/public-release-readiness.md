# Research preview release readiness

Status: local 0.1.0rc2 candidate verified on Python 3.12.14; private and unpublished.
This is not a native qualification, security certification or publication approval.

| Area | Candidate implementation/evidence | Remaining boundary |
| --- | --- | --- |
| Public API | 15 supported root exports checked; specialist utilities use their owning modules; no compatibility re-export module | Future stability needs release/version discipline |
| Result inspection | `inspect_result` and `Evaluation.report()` expose native result, metrics, traces and evidence coverage | Unknown native coverage stays unknown; no native scientific verdict conversion |
| Capabilities | Exposed on the engine and `check()`; unsupported execution is rejected | No interactive batching/concurrency or GPU scheduler promised |
| Distribution | Wheel and sdist built locally; wheel rebuilt from sdist; both wheels installed into isolated venvs; arithmetic, save/reopen and CLI smoke passed | Tested on Python 3.12.14; Python 3.10/3.11 runtime checks pending |
| Installed integration | Not included in this verification run | Excalidraw plugin discovery and inert check remain synthetic; no native gym or learned agent execution |
| Robotics | Existing isolated native recipes and retained-evidence contracts | SmolVLA/pi0.5 manifests, checkpoints/environment qualification, calendars, Protocol E, parity and compiled count remain unverified |
| Licensing | Restricted research-use license and contribution terms included in package metadata/artifacts | Custom legal terms and file-level historical contributor/third-party rights need independent review before public redistribution |
| Public release | No GitHub release, PyPI upload or visibility change performed | Owner publication decision and final source/dependency/security review still required |

See [distribution verification](distribution-verification.md) for exact local
commands and artifact checks, and [preview scope](research-preview.md) for API
and integration guarantees. A useful narrow research preview does not require
claiming that unfinished native robot experiments are ready.
