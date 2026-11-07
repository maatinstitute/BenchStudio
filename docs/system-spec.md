# System-level evaluation contracts

BenchStudio evaluates **systems**, not only one robot policy. A SystemSpec is a
versioned graph of components and typed port connections. Components may be
VLA policies, world models, world-action models, simulation backends,
planners, agents, tools, or ordinary deterministic programs.

- Cycles are permitted for feedback and agent loops.
- Multiple agents and disconnected parallel branches are permitted.
- System identity hashes node revisions, routing, and JSON metadata.
- SystemSpec is declarative: it **does not execute, sandbox or orchestrate**
  any model, control robots, or infer the quality of an environment.
- Individual components keep their own implementation/runtime and licensing.
- Evaluation evidence, outcome authority and schedule are separate contracts.

This generalizes the component/driver/evaluator separation already present in
[AlpaBridge](https://github.com/amtellezfernandez/AlpaBridge). The original
BenchStudio Policy/Simulator API stays supported for simple single-policy
closed-loop tasks. Do not assume a graph connection implies that two
independently clocked systems actually exchanged data.
