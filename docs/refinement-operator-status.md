# Refinement/Refresh operator status

Audited against Warren's 8 November 2026 09:38:55 UTC email and the retained E0
manifest. This is a technical handoff, not an authorization or a campaign release.

## What Warren should not have to implement

BenchStudio maintainers own generic execution, package verification, interpreter
routing, import diagnostics, logs and retained results. Paper maintainers own the
installed scientific recipe, native state generator, adapters and offline analysis.
Warren should not be asked to write another launcher, manifest parser, external
source verifier, registry plugin or result-conversion script. A backend package is
implemented once by maintainers, then selected by installed name by researchers.

## Current facts

| Item | Status | Remaining work |
|---|---|---|
| E0 staged sources | 48 hashes independently matched pinned GitHub sources | Host copy still needs verification; compressed package bytes were not supplied |
| E0 proposed authorization | Eight bound hashes agree with manifest; scope is PROTOCOL_E0_PI05 | Alba's confirmation of that exact proposal remains separate from code preparation |
| E0 execution | Warren reports not run; permission not consumed | Warren alone performs the existing authorized run after its existing prerequisites |
| Import-only diagnostic | Earlier pi0.5 probe failed through a Windows profile.py shadow module | Separate import-only permission question remains with Alba; no expansion is inferred |
| R22/R25 installed recipe | Audited and merged through paper [PR #16](https://github.com/amtellezfernandez/refinement-refresh-robot-policies/pull/16) into implementation commit ab05b1368abf28df4926273dc36b4e0b4bbb5ce4 | Install from that implementation checkout; it is not on paper main or native-qualified |
| Model-native state generator and manifests | Warren reports missing | Maintainer implementation can be developed offline; actual native state work retains its existing scope restrictions |
| Native parity, evaluator and count qualification | Unverified | Host evidence is required; generic Python/CLI tests are not substitutes |

The installed example names in the generic guide are illustrative. The installed pipeline name refinement-refresh is provided by PR #16;
it requires that integration package and remains unqualified natively.
Do not give Warren fabricated per-model backend names or claim the campaign is
ready through the generic engine. Do not wrap the whole 400-pair study
as one generic trial: that would lose its experimental identity/accounting rules.
Keep its scientific runner as the authority for those rules.

## Existing E0 workflow

The package stays pinned to BenchStudio
9937944a902fce7eb4c0339df27cdcaedc2d9461 and paper harness
3b4a78eff57b5e3d883cbc3059987167141bb18f. Do not rewrite its files or its authorization
because the generic library advanced. The current BenchStudio controlling process
can verify the unchanged staging manifest before launching that existing driver;
see [source preparation](native-preparation.md#existing-warren-e0-package).
No external pre-launch verification script is needed with that route. The existing
NC1 checks and the persistent consumption registry still apply.

The host operator supplies actual local paths, runs only the already-authorized
host work and retains its records. We cannot verify the host's persistent ledger
from GitHub or manufacture host-native qualification evidence offline.

## Offline status without another integration script

```python
import benchstudio as bs
from benchstudio.refinement import RefinementWorkspace

status = RefinementWorkspace("/path/to/paper-checkout").prepare()
print(status.summary())
```

The workspace defaults to the scientific runner's existing canonical directory.
This only invokes its offline preparation helper. It does not generate states or
identities, invoke returned launch commands, qualify either model or grant a
permission. The paper checkout must already include that reviewed helper.

The campaign is ready only when both native stacks, model/checkpoint pins, Protocol
E, pi0.5 parity/count attestations, the native 400-pair/800-attempt schedules and
completeness/coverage analysis meet the scientific protocol. Technical readiness
and execution authorization remain distinct.
