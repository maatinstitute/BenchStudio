# One workspace, two native stacks

This is the operator route for the unreleased R22/R25 draft. Preparation reads
existing files, gives all missing inputs in one report, and prints commands.
It never generates states/identities, imports a native stack, creates an approval,
marks a qualification PASSED, or executes its suggested commands. No approval
file or execution permission is supplied by this change.

Use the existing release gate's workspace at
`REPOSITORY/experiments/runs/cross_policy_confirmation_v2/` (outside frozen
evidence packages). The helper defaults to it; arbitrary external paths cannot
pass the release gate. Under each `pi05/` and `smolvla/`
folder place the existing `manifest.json`, `schedule.json`, `initial_states.npz`
and `fixtures.json`. For pi05 also supply the attesting server's
`startup_gate.json`; for SmolVLA put the pinned checkpoint in `checkpoint/`.
These are operator path conventions, not new scientific evidence formats.
Schedules remain 400 paired identities / 800 attempts per model and retain the
native harness schema. Neither model is pooled with the other.

From the paper checkout, with the selected model's pinned native interpreter:

```sh
/path/to/native/python experiments/tooling/cross_policy_v3/prepare_campaign.py --model pi05
```

The helper always returns its report even when inputs are missing. An exit code
of zero means the report was produced, not that the campaign is ready. Check
`offline_inputs_complete`, qualification items, and `execution_authorized`
separately. No single preparation report qualifies native execution.

The report contains shell-quoted commands and the same commands as argument
arrays. It supplies the required attempt journal in the analysis command and
both native manifests in the Protocol E input-only command. It reuses the
existing manifest/schedule/qualification/Protocol E validators rather than adding
new acceptance rules. The real runner still applies all release and qualification
gates. Integrate the reviewed launcher/code-hash work from draft PR #6/#8 before
using the launch command; this helper reports an absent launcher as a blocker.
The pi05 attesting server must already be running after separately authorized
qualification; this helper does not start it or issue new native commands.

After both companion PRs are installed, the same route from BenchStudio is:

```python
import benchstudio as bs
from benchstudio.refinement import RefinementWorkspace

work = RefinementWorkspace(
    repository="/path/to/refinement-refresh-robot-policies",
    workspace="/path/to/refinement-refresh-robot-policies/experiments/runs/cross_policy_confirmation_v2",
    python="/path/to/pi05-native/python",
)
report = work.prepare(model="pi05")
print(report.summary())
commands = report.commands("pi05")
```

Use a separate instance with SmolVLA's native interpreter for that stack. The
`repository` must be a trusted, reviewed checkout: preparation runs that checkout's
stdlib helper in a subprocess. BenchStudio's supported interpreter remains
separate from the OpenPI Python 3.8 process. `prepare()` never runs the returned
commands. First pin/check native environments, checkpoints, source and assets;
then obtain their separately authorized native qualification evidence and existing
manifests; finally use the real launcher only under a valid campaign release.
Missing native tools (parity, mapping, manifest generation) are implementation
work still owed: the helper reports their absence/evidence status, not a replacement.

No frozen evidence, E0 registry, release, qualification record or reserved identity
is written by preparation. The duplicate-campaign limitation documented in the
harness is not resolved by this operator route.
