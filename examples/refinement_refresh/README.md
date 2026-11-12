# Refinement versus refresh: a SmolVLA worked example

This directory shows how the paper *Refinement versus Refresh: Deployment-Time
Compute Allocation for Chunked Robot Policies* uses BenchStudio's paired-outcome
analysis. The study is a worked example of an evaluation procedure, not evidence
that the reported configuration transfers to other checkpoints, policies,
tasks, simulators, or physical robots.

The deployment controls in this case are:

- `d`: denoising steps used to generate a predicted action chunk;
- `h`: actions executed before obtaining a new observation and generating again;
- `K = 50`: predicted actions per chunk, held fixed throughout the study.

Other policy families may expose different refinement controls. Their values
must be compared within a model and under that model's own cost boundary.

The camera-ready manuscript is available as [`paper.pdf`](paper.pdf).

## What is included

`confirmation_outcomes.jsonl` contains only the fields required to reproduce
the paper's held-out counts and paired primary comparison. It was derived from
the 1,120 canonical episode records in the paper repository. Simulator states,
action tensors, images, model weights, and runtime logs are intentionally not
copied here.

`expected_summary.json` records the published totals and the SHA-256 identities
of the source archive and its canonical episode member. The historical episodes
were produced by the study's pinned native LeRobot/LIBERO runtime. They are not
BenchStudio-produced runs, and this example does not establish native-runtime
parity.

## Reproduce the reported totals

From a BenchStudio checkout:

```bash
python -m pip install -e .
python examples/refinement_refresh/verify.py
```

The check reconstructs:

- 1,120 canonical held-out attempts across seven settings;
- 171,805 recorded environment actions;
- 139/160 successes for `(h=2, d=2)` and 122/160 for `(h=2, d=5)`;
- 24 paired wins, seven paired losses, and 129 ties;
- a success difference of 0.10625 for the prespecified primary comparison.

BenchStudio also reports its exact discordance interval. The paper's
`[0.04375, 0.16875]` interval is retained separately because it used a
specified task-conditional bootstrap. The two intervals answer the same
comparison under different uncertainty constructions and must not be silently
substituted for one another.

## Evidence boundaries

The denoising comparison at fixed `h=2` was prespecified before held-out
outcomes. Prefix comparisons were added later and are descriptive. This example
therefore verifies the frozen aggregate and paired identities without promoting
later analyses to confirmatory status.

Re-executing the study requires the pinned native policy and simulator stack.
BenchStudio should become the common campaign and evidence layer only after an
explicit native-path parity qualification. Until then, the retained native-runtime records and their digests
remain the authority for the original outcomes; this directory is the maintained public
entry point for the paper and its reproducible aggregate example.
