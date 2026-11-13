# Refinement versus Refresh: Deployment-Time Compute Allocation for Chunked Robot Policies

## Paper metadata

- **Author:** [Alba María Téllez Fernández](https://amtellezfernandez.com/)
- **Affiliation:** [MAAT Institute](https://maatinstitute.com/)
- **Workshop topic:** *Post-Training Adaptation of Robot Foundation Models*, a NeurIPS 2026 workshop
- **Topics:** deployment-time compute allocation, post-training adaptation, vision-language-action policies, inference compute, test-time compute, action chunking, refinement, replanning, and closed-loop robot control
- **Paper:** [`paper.pdf`](paper.pdf)

## Cite the paper

```bibtex
@misc{tellezfernandez2026refinement,
  author = {T{\'e}llez Fern{\'a}ndez, Alba Mar{\'i}a},
  title = {Refinement versus Refresh: Deployment-Time Compute Allocation for Chunked Robot Policies},
  year = {2026},
  note = {Accepted at Post-Training Adaptation of Robot Foundation Models, a NeurIPS 2026 workshop},
  url = {https://github.com/maatinstitute/IVal/tree/main/examples/refinement_refresh}
}
```

Use the arXiv identifier as the canonical citation once it is assigned.

This page is the public reproducibility entry point for the paper and its
SmolVLA/LIBERO case study.

This directory shows how the paper *Refinement versus Refresh: Deployment-Time
Compute Allocation for Chunked Robot Policies* uses IVal's paired-outcome
analysis. The study is a worked example of an evaluation procedure, not evidence
that the reported configuration transfers to other checkpoints, policies,
tasks, simulators, or physical robots.

The deployment controls in this case are:

- `d`: denoising steps used to generate a predicted action chunk;
- `h`: actions executed before obtaining a new observation and generating again;
- `K = 50`: predicted actions per chunk, held fixed throughout the study.

Other policy families may expose different refinement controls. Their values
must be compared within a model and under that model's own cost boundary.

## What is included

`confirmation_outcomes.jsonl` contains only the fields required to reproduce
the paper's held-out counts and paired primary comparison. It was derived from
the 1,120 canonical episode records in the paper repository. Simulator states,
action tensors, images, model weights, and runtime logs are intentionally not
copied here.

`expected_summary.json` records the published totals and the SHA-256 identities
of the source archive and its canonical episode member. The historical episodes
were produced by the study's pinned native LeRobot/LIBERO runtime. They are not
IVal-produced runs, and this example does not establish native-runtime
parity.

## Reproduce the reported totals

From a IVal checkout:

```bash
uv sync --locked
uv run --locked python examples/refinement_refresh/verify.py
```

The check reconstructs:

- 1,120 canonical held-out attempts across seven settings;
- 171,805 recorded environment actions;
- 139/160 successes for `(h=2, d=2)` and 122/160 for `(h=2, d=5)`;
- 24 paired wins, seven paired losses, and 129 ties;
- a success difference of 0.10625 for the prespecified primary comparison.

IVal also reports its exact discordance interval. The paper's
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
IVal should become the common campaign and evidence layer only after an
explicit native-path parity qualification. Until then, the retained native-runtime records and their digests
remain the authority for the original outcomes; this directory is the maintained public
entry point for the paper and its reproducible aggregate example.
