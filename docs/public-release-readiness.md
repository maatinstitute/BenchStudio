# Public release readiness

**Status: blocked; no public release has been prepared or authorized.**

This audit is scoped to the repository default branch at commit
`585b4d170b639f8b5d53b0adc2f93a6c58413540`. It records release blockers so
they can be resolved in reviewable steps. It is not a legal opinion, a security
certification, or permission to change repository visibility.

## Release blockers

| Area | Current evidence | Required before publishing |
| --- | --- | --- |
| Repository access | GitHub reports this repository as private. | Treat changing visibility as a separate release action after the gates below pass. |
| Outbound license | `LICENSE` says “ALL RIGHTS RESERVED” and expressly withholds permission to publish, copy, modify, and distribute. `pyproject.toml` describes the package as proprietary. | The owner must select the license and scope for the release. Do not replace the license until source provenance and contributor rights are reconciled. |
| Imported source | `docs/source-attribution.md` identifies direct ports from AlpaBridge, URDF Studio, and Refinement vs Refresh/RoboPAD. AlpaBridge's current license is BSD-3-Clause; URDF Studio's current license is proprietary/non-commercial; no root `LICENSE` or `COPYING` file was found in the RoboPAD default-branch tree. | Create a file-level provenance and rights inventory for all direct ports, including commit and source-file digests. Preserve BSD notices where applicable. Confirm which owner-controlled source can be relicensed and identify any third-party portions or contributions that cannot be included. |
| Contributions | The default branch currently contains only contributions already merged there; unmerged PRs are not part of this audit's release contents. | Record contributor provenance and the applicable contribution terms for every merged contribution before selecting the outbound license. |
| Package identity and metadata | `pyproject.toml` declares version `0.1.0`, Python `>=3.10`, no project URLs, no classifiers, and optional dependency ranges without upper bounds. | Decide the public package/repository identity, add accurate project URLs and classifiers, review supported Python versions and dependency constraints, then build and inspect wheel and sdist metadata. Do not publish to PyPI until the name and release metadata are verified. |
| Installation verification | Base-branch CI tests source checkout on Python 3.10–3.12 but does not build or install distributions. This PR adds wheel/sdist build and clean-environment CLI smoke steps; their CI result is pending. | Require the new distribution checks to pass on the release branch and exercise the documented API/examples from installed artifacts. |
| User-facing API | The README is 24 KB and leads with numerous subsystem workflows. The package root re-exports a broad set of internal and research-facing primitives. | Define the supported public API surface and a short first-run path. Move specialist/reference material into focused guides; identify experimental integrations and their external runtime requirements. |
| Release hygiene | The tracked tree has no `SECURITY.md`, release process, or dependency/license inventory. The tree scan found no obvious credential, checkpoint, or binary-asset filenames; that is not a content-level secret or rights scan. | Add a vulnerability-reporting route and release procedure. Run content-level secret scanning, a dependency/SBOM and license review, and inspect examples, source snapshots, generated artifacts, and histories before public visibility. |

## Safe release sequence

1. Freeze the intended release scope and create a file-to-source provenance
   inventory.
2. Resolve source and contributor rights; choose the outbound license and
   matching package metadata.
3. Narrow the supported public API and make the installation and example
   guides runnable from a clean install.
4. Pass the wheel/sdist build-install checks and release CI; review security,
   dependency, and secret-scan results.
5. Tag a versioned release candidate and inspect its exact archive contents.
6. Change repository visibility or publish a package only as an explicit,
   separate release action.

## Evidence checked

- [Repository metadata](https://github.com/amtellezfernandez/BenchStudio)
- [Current license](https://github.com/amtellezfernandez/BenchStudio/blob/main/LICENSE)
- [Package metadata](https://github.com/amtellezfernandez/BenchStudio/blob/main/pyproject.toml)
- [Source attribution](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/source-attribution.md)
- [Architecture boundaries](https://github.com/amtellezfernandez/BenchStudio/blob/main/docs/architecture.md)
- [CI workflow](https://github.com/amtellezfernandez/BenchStudio/blob/main/.github/workflows/ci.yml)
- [AlpaBridge license](https://github.com/amtellezfernandez/AlpaBridge/blob/main/LICENSE)
- [URDF Studio license](https://github.com/amtellezfernandez/urdf-studio/blob/urdf-studio-main/LICENSE)
- [RoboPAD source tree](https://github.com/amtellezfernandez/refinement-refresh-robot-policies/tree/main)

Re-run this audit against the exact release candidate before publishing; this
document describes the inspected commit, not a permanent certification.
