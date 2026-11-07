# Composed-system event traces

`SystemEvent` is an optional **offline evidence** representation for a
single trial. Record component events, parent event IDs, ports, clock domain
and optional payload hash. The `audit_system_trace()` validator checks
declared graph connections and flags missing, conflicting or ungrounded
lineage. It explicitly lists graph connections not observed in the trace.

This provides an experimental trace across a world model, an agent, a
world-action model and an actuator without choosing any particular model
or backend. It is NOT a multi-agent orchestrator or real-time controller.
It does not infer that uninstrumented communications took place.

Events from different clock domains are not ordered by raw timestamps.
No causal effect is inferred from parent pointers alone; causal claims need
controlled interventions and matched experimental designs.

Why not rebuild Robocurve/Inspect Robots? That framework already supports
graded runs, visualizations and many policy/embodiment plugins. BenchStudio
should accept such runs and add system-level lineage, controlled ablations
and experiment validity checks, without duplicating its telemetry viewer.
