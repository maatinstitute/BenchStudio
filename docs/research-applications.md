# Research applications, not research-specific core APIs

BenchStudio's core is intended to evaluate systems (robot policies, world models,
agent workflows, or composed systems) with one execution/evidence contract.
Studies may reside in `examples/` and use the same `benchstudio` package.
**Outcome Recovery** (`examples/outcome_recovery/`) is the first such application:
it uses existing `compile_campaign_spec`, `compile_counterfactual_plan`, and
`execute_counterfactual_plan` without duplicating a scheduler, model wrapper,
or result serializer. The folder name describes the experiment, **not a product
or a framework**.

## Observed legacy ownership problems

The current published package still includes research-specific planning,
controller, rollout, outcome-conditioning, and compute-allocation helpers.
Their long-term ownership should follow the distinction below:

| Existing responsibility | Appropriate long-term owner | Migration gate |
| --- | --- | --- |
| Recovery-specific plans and reference batches | Outcome Recovery study recipe | Frozen schedule digests, exact IDs, consumed/reserved slots, no extra attempts |
| Study-specific reference controllers and caches | Study repository | Reference action parity, pose/conformance validation |
| Recovery-specific rollout and initialization | Outcome Recovery recipe unless generic behavior is extracted | Same reset, step, success, and partial-failure semantics |
| Outcome-conditioning plans and schedules | Outcome-conditioning study recipe | Frozen training/evaluation schedules and record hashes |
| Compute-allocation plans | Compute-allocation study recipe | Historical schedule hash, holdout membership, parity |
| Counterfactual planning, frozen plans, and campaign execution | BenchStudio core | Stable public contracts and existing tests |
| Simulator adapters | BenchStudio optional integrations | Native environment semantics and explicit capabilities |

This inventory is **a migration plan, not a claim that these responsibilities
were moved in this change**. Do not rename or drop historical frozen-plan schema
IDs or research evidence to improve a display name. Do not publish contents of
private source repositories, checkpoints, or evidence bundles as part of a
rename.

## Consolidation stages

1. Use the new application path and existing common campaign APIs for future
   recovery study variants. Keep already-frozen results immutable.
2. Qualify a native upstream LIBERO evaluator with initial observation/state,
   preprocessing, action, termination, and native success parity against the
   frozen source run; require a real checkpoint and assets for this gate.
3. Move only research-specific modules and tests out of the importable core,
   in reviewed batches; eliminate old module imports in that same change.
   No forwarding aliases or second maintenance paths. Retain provenance links
   to historical source revisions separately from runtime code.
4. Do not describe a protocol-only or synthetic example as a demonstrated
   policy-recovery improvement.

The general library should not require the experiment's checkpoint, train a
policy, invent a simulator scorer, or automatically select a new physics engine.
