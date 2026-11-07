# Controlled component ablations and evidence coverage

BenchStudio can ask what changes when one component of a composed system is
replaced. `audit_ablation()` compares full versioned component/port graphs
and checks that differences are limited to explicitly approved component IDs.
Any undocumented model, routing or metadata difference is flagged.

`audit_trial_coverage()` checks planned experimental identities versus
observed results and never counts runtime failures as task failures.

`review_ablation_evidence()` inspects declared structural isolation and
matched-outcome completeness. **Passing its count threshold is NOT a power
calculation or proof of a causal effect.** Physical state/reset parity, time
synchronization, sample independence, metric validity, and external-source
qualification still need to be validated before strong scientific conclusions.

Distinct use cases:
* World model + planner vs same planner without prediction, under matched tasks
* Multi-agent system A vs B with only the communication mechanism changed
* VLA serving interval R22 vs R25 with frozen model and task identity
* WAM predictions vs executed action consequences, with compatible metrics

This is where BenchStudio can be additive to a framework such as RoboCurve
Inspect Robots, whose public documentation already covers running policies,
grading, replayable traces, visualization and offline re-scoring.
