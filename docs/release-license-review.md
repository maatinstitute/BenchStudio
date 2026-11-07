# Public release and license review (proposal)

**Status: draft proposal only.** This branch does not publish the repository,
change its visibility, or authorize a package release. The Apache-2.0 files in
this branch are a proposed outbound license. Do not treat this branch as proof
that every file has been cleared for redistribution.

## Proposed licensing model

The proposal uses Apache License 2.0 for BenchStudio-owned code and
documentation, following the permissive license used by Hugging Face
Transformers. AlpaBridge-derived files retain their BSD-3-Clause obligations;
the applicable license text is included under `LICENSES/`. Each source-derived
file still needs its required copyright and attribution notices preserved.

This license selection is a product/maintainer decision, not a substitute for
provenance or contributor-rights review. The public release must wait until the
review below is complete and the maintainer explicitly approves the final
license and repository state.

## Provenance items requiring file-level clearance

| Source family | Evidence currently recorded | Clearance needed before release |
| --- | --- | --- |
| BenchStudio original work | Repository history and source-attribution record | Verify each file has no copied material with incompatible terms; check commits and vendored content. |
| AlpaBridge | Attribution record identifies BSD-3-Clause source files and digests | Preserve upstream notices and BSD-3 conditions for every derived file; verify current file-to-source mapping. |
| URDF Studio / urdf-ops | Attribution record identifies extracted code; upstream repository is proprietary/noncommercial | Confirm the exact included portions are Alba-owned or otherwise licensed for redistribution and commercial use. Do not assume repository ownership clears third-party contributions. |
| RoboPAD / Refinement vs Refresh | Attribution record identifies numerous direct ports; no root LICENSE/COPYING was found in the reviewed tree | Map every copied file to contributor and agreement scope. In particular, map Warren Smith's covered contributions to the signed agreement's Schedule B and confirm the agreement grants the intended open-source and commercial sublicensing rights for those exact files. |
| WorldEpisode and other integrations | Attribution record describes bindings and extracted contracts | Verify each implementation is original, public-API-based, or separately licensed; enumerate any additional source-derived files. |
| Dependencies and assets | NOTICE says third-party datasets, checkpoints, robot drivers, simulator binaries, and AGPL urdf-os code are not copied | Re-run an inventory against the actual release tree, including optional dependencies, generated assets, examples, and history. |

The table is a review checklist, not a legal conclusion.

## Required release gate

Before changing repository visibility or publishing to an index:

1. Produce a file-level provenance inventory containing source repository,
   source commit/path, source digest, BenchStudio path/digest, author/contributor,
   applicable license or agreement, retained notices, and reviewer decision.
2. Map Warren's signed agreement and its Schedule B to each included RoboPAD
   derivative. Escalate any unmapped or ambiguous contribution for explicit
   written resolution.
3. Confirm the URDF Studio-derived files are owned by Alba or covered by
   redistribution rights. Remove or replace anything that is not cleared.
4. Scan the release tree and reachable Git history for secrets, credentials,
   private datasets, checkpoints, robot logs, and non-redistributable assets.
5. Validate the built wheel and source archive, including their license and
   notice contents, from a clean environment.
6. Have the maintainer review and approve the exact commit, license, notices,
   and repository visibility change. A passing CI run is not release approval.

## API documentation convention

Public Python examples should consistently use the package alias:

```python
import benchstudio as bs

audit = bs.pipeline("campaign-audit")
result = audit("./runs/completed-campaign")
print(result.summary())
```

This documents the intended concise import style. The audit is read-only and
does not load a checkpoint, replay a policy, or start a simulator.

## Comparison target

Transformers is a useful reference for the user-facing import convention,
task-oriented factory, installation guidance, organized examples/tests, and
release metadata. BenchStudio should copy those usability patterns while
stating clearly that environment setup, robot/simulator runtimes, checkpoints,
and task scoring remain explicit caller-owned prerequisites.
