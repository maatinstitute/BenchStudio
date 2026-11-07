# Matched system comparisons

`compare_system_runs(a, b)` compares **systems**, including a single VLA,
a world model + planner + controller, a world-action model, or multiple
agents. It works entirely on saved SystemRun evidence.

Matching uses exact TrialKey identity: task/evaluator revisions, scenario,
condition, seed, repetition, environment revision and execution protocol.
A match means the run records declare comparable units; independent state
replay/parity validation is still necessary to claim physical equivalence.

The function reuses BenchStudio's established paired-binomial interval and
paired outcome summary rather than introducing a competing scorer.
Execution failures and missing outcomes remain missing and cannot inflate
or depress task-success denominators silently.

Optional numeric metrics (world prediction error, latency, trajectory error)
are compared only when explicitly requested. Deltas are raw
`system_b - system_a` and have **no automatic direction**: a negative
prediction error is better while a negative success probability is worse.

This is descriptive matched analysis, NOT automatically a causal ablation
or a validated comparison of different robots. Controlled component changes
and evidence prerequisites are added in the next PR.
