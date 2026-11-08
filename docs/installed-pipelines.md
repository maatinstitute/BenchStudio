# Installed scientific pipelines

The built-in System + Benchmark engine remains the default. Scientific studies
with their own native attempt accounting may expose an installed pipeline instead
of being collapsed into one generic system trial.

BenchStudio discovers trusted installed factories in benchstudio.pipelines.
A factory receives Python options and returns an object with check() and run().
Construction must be inert. Recipe authors own scientific identities, native gates
and result interpretation. Missing/ambiguous names or invalid factory contracts
fail explicitly.

For CLI integration, the factory provides add_cli_args(parser) and
options_from_args(namespace). The unified CLI builds the same pipeline as Python.
check() returns a preparation report with summary(), technical_ready and
execution_authorized kept separate. --check never calls run(). Scientific guards
remain in the recipe. Factory imports execute trusted installed package code;
initialization must remain lightweight.

## Refinement versus Refresh

The concrete native recipe is implemented in paper
[PR #16](https://github.com/amtellezfernandez/refinement-refresh-robot-policies/pull/16),
stacked on its three-interpreter frontend drafts. It remains draft and is not on
paper main or scientifically qualified by this integration.

After maintainers integrate/review the recipe, the operator installs its package
in the controlling BenchStudio Python >=3.10 environment and uses
bs.pipeline("refinement-refresh", ...), or
benchstudio evaluate --recipe refinement-refresh ... --check.
Configuration selects the exact paper checkout commit and three actual native
interpreters; no operator-written scripts or result converters are required.
The [package guide](https://github.com/amtellezfernandez/refinement-refresh-robot-policies/blob/d9f22583be0d9c0cbfad456386e0ae722eff8c24/integrations/benchstudio/README.md)
contains the concrete parameters.

The recipe invokes the existing two-model frontend and preserves both native
analyses and their hashes separately. Preparation/installation never calls E0,
native qualification, state generation or confirmation. run() requires existing
technical readiness and authorization; the native frontend independently checks
again. No permissions are created or broadened. Missing native state tools,
manifests and qualification evidence remain blockers. Wiring is not a release.
