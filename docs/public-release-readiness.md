# Research preview release readiness

Status: locally verified 0.1.0rc1 candidate; private and unpublished.
This supersedes the historical audit at commit
585b4d170b639f8b5d53b0adc2f93a6c58413540, which described the old license/API.
It is not a native qualification, security certification or publication approval.

| Area | Candidate implementation/evidence | Remaining boundary |
| --- | --- | --- |
| Public API | 15 supported root exports; explicit old imports resolved through compat; all supported names checked | Future stability needs release/version discipline |
| Result inspection | inspect_result and pipeline.report expose native result, metrics, traces and evidence coverage | Unknown native coverage stays unknown; no native scientific verdict conversion |
| Capabilities | Exposed on engine and check(), including CLI check serialization; unsupported execution rejected | No interactive batching/concurrency or GPU scheduler promised |
| Distribution | Wheel and sdist built locally, wheel rebuilt from sdist, both installed into isolated venvs; actual arithmetic/save/reopen/CLI smoke passes | Tested on Python 3.12.14; other supported-version runtime checks pending |
| Installed integration | Excalidraw package built/installed; real entry-point discovery and inert four-case check pass in both venvs | No native gym or learned agent execution |
| Robotics | Existing isolated native recipes and retained-evidence contracts | SmolVLA/pi0.5 manifests, checkpoints/environment qualification, calendars, Protocol E, parity and compiled count remain unverified |
| Licensing | Current restricted research-use license and contribution terms included in package metadata/artifacts | Custom legal terms and file-level historical contributor/third-party rights need independent review before public redistribution |
| Public release | No GitHub release, PyPI upload or visibility change performed | Owner publication decision and final source/dependency/security review still required |

See [distribution verification](distribution-verification.md) for exact local
commands and artifact checks, and [preview scope](research-preview.md) for API
and integration guarantees. A useful narrow research preview does not require
claiming that unfinished native robot experiments are ready.
