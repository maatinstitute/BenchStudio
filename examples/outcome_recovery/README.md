# Outcome Recovery — reference application

**Question:** After a fixed action prefix, does an interactive policy recover from a
controlled perturbation compared with the matched nominal continuation?

This example demonstrates **how to express that study with BenchStudio's existing
campaign and counterfactual APIs**, not a second simulator, policy runner,
result format, or standalone scientific framework. The public example contains
no private checkpoint, episode traces, training data, simulator assets, or
unqualified recovery results.

## 1. Freeze the design without executing anything

```bash
python examples/outcome_recovery/run.py \
  --plan-only --output runs/outcome-recovery-plan
```

Produces `campaign-plan.json`, `counterfactual-plan.json`, and `provenance.json`.
The included design is **illustrative**: two seeds, a single paired
object-translation intervention at transition 5, and a placeholder task. It is
not a LIBERO-ready scene or valid success-rate demonstration. You must replace
task, object identity, checkpoint and intervention parameters with qualified
ones for the selected environment.

## 2. Execute with a trusted native evaluator

```bash
python examples/outcome_recovery/run.py \
  --frozen-plan /path/to/your/campaign-plan.json \
  --interventions /path/to/your/interventions.json \
  --evaluator your_project.native_eval:evaluate \
  --output runs/outcome-recovery-native
```

The callback receives a `CounterfactualCell` together with the **frozen attempt**
and **frozen protocol** as keyword arguments. It **must** return a
`CounterfactualEvaluation(success=..., recovery_time_ms=..., metadata=...)`.
For example:

```python
from benchstudio.campaigns import CounterfactualEvaluation

def evaluate(cell, *, attempt, protocol):
    # Use attempt.task_seed, attempt.policy_seed, and the pinned
    # protocol to execute a fresh native LIBERO episode for this branch.
    # Implement actual reset/replay/intervention/success checks upstream.
    raise NotImplementedError("Provide the real native evaluator here")
```

The code above is an interface illustration, not a working policy evaluator.
Use the upstream simulator and model runtime, not a copied environment. For
LIBERO, the callback owns the native LeRobot/LIBERO preprocessing, exact reset,
committed-prefix replay, perturbation, controller lifecycle, terminal handling,
and the environment's native success predicate. The paired nominal and
intervention calls must each reset and replay from the same independently
verified source. Never apply an intervention to the reused state of an earlier
branch.

A claim-bearing callback returns two **actual boolean** task outcomes for each
pair plus evidence metadata (not inferred by this example):

| Metadata key | Contract |
| --- | --- |
| `initial_state_sha256` | Identical native initial state in both branches |
| `fork_state_sha256` | Identical native state at the intervention boundary |
| `prefix_actions_sha256` | Identical executed action prefix |
| `checkpoint_sha256` | Identical policy checkpoint |
| `simulator_revision` | Same pinned runtime/assets |
| `native_success_source` | Same explicit native success predicate |
| `intervention_applied` | False in nominal branch; true in intervention |
| `intervention_id` | Matches the planned intervention ID |

The example checks **metadata agreement and declared execution semantics**, not
the truth of those claims or the fidelity of a physical experiment. The
callback itself must be reviewed; the source-file digest is recorded in
`provenance.json`. If any outcome is missing or the metadata disagrees,
`qualification.json` is unqualified and the program exits nonzero. Nothing
converts a missing outcome into a failure or an automatic retry.

The current version deliberately accepts **exactly one intervention per matched
attempt**. The shared counterfactual API permits more; this example avoids
counting repeated nominal executions as independent observations. To extend it,
first define an explicit repeated-control policy and statistical unit.

## Ownership

BenchStudio owns frozen campaign identity, branch ordering, evidence serialization,
and paired-contract checks. The **native evaluator belongs to the scientific
study** until there is a broadly useful upstream or shared integration to
reuse. Do not copy source-specific research controllers into the BenchStudio
core. This example is the destination for study-specific recipes, while
immutable historical results and manuscripts remain in their original
research repository.

See [the migration boundary](../../docs/research-applications.md) for the existing
study-specific modules that still need parity-gated extraction.
