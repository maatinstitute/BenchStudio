# Cluster execution

ReVa runs a cluster campaign from one frozen plan. Scheduler jobs select
disjoint deterministic shards while writing evidence to one shared campaign
directory. The plan digest, attempt identities, runtime receipts, leases, and
append-only ledger remain identical to a local run.

## Storage and runtime contract

- Put the frozen plan and output directory on a shared POSIX filesystem whose
  advisory locks are reliable on every worker (for example, a correctly
  configured Lustre, GPFS, or NFS mount).
- Install the same locked environment on every node with `uv sync --locked`.
- Let the scheduler set GPU visibility. ReVa validates declared resource
  requirements but does not allocate GPUs.
- Use one shard per scheduler task. A retried task uses the same shard index and
  resumes from committed evidence.
- For preemptible simulator jobs, pass `--recover-interrupted`. A `SIGTERM`
  releases the active lease; the next run preserves the incomplete directory
  under `interrupted-attempts/` before rerunning the same frozen attempt.
- Preemption recovery uses one process worker per scheduler task (`--workers 1`,
  the default), so signal ownership and lease release remain unambiguous.
- Interrupted-attempt recovery is rejected for physical environments.
- Final audit rejects Python or package-version drift between workers assigned
  to the same declared environment. Different declared environments remain
  separate comparison strata.
- Run audit, archive, and publication once, after every shard succeeds.

Independent node-local disks and object storage do not provide the shared lock
and ledger semantics required by this execution mode. Kubernetes therefore
needs a ReadWriteMany volume with working POSIX locks.

## Worker image

The checked-in `Dockerfile.cluster` builds a pinned, nonroot core worker:

```bash
docker build --file Dockerfile.cluster --tag reva:cluster .
docker run --rm reva:cluster --help
```

Use `--build-arg IVAL_EXTRA=mujoco` (or another declared optional extra)
when that backend belongs in the worker. VLA checkpoints, CUDA libraries, and
simulator assets are model-specific; extend this image with their pinned native
runtime instead of adding unverified dependencies at job startup.

## Freeze before scheduling

```bash
uv run --locked python -m reva.cli \
  --campaign-spec campaign.json \
  --plan-output /shared/study/campaign-plan.json
```

Do not compile the specification independently in each job. Every job loads the
same serialized plan:

```bash
uv run --locked python -m reva.cli \
  --frozen-plan /shared/study/campaign-plan.json \
  --execute-registry \
  --shard-index "$SHARD_INDEX" \
  --shard-count "$SHARD_COUNT" \
  --worker-id "$WORKER_ID" \
  --recover-interrupted \
  --output /shared/study/run
```

The command exits successfully when its assigned attempts are complete, even
while other campaign shards remain outstanding. It prints both shard-local and
campaign-wide missing counts.

## SLURM array

```bash
#!/usr/bin/env bash
#SBATCH --array=0-7
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
set -euo pipefail

uv run --locked python -m reva.cli \
  --frozen-plan /shared/study/campaign-plan.json \
  --execute-registry \
  --shard-index "$SLURM_ARRAY_TASK_ID" \
  --shard-count "$SLURM_ARRAY_TASK_COUNT" \
  --worker-id "${SLURM_JOB_ID}-${SLURM_ARRAY_TASK_ID}" \
  --recover-interrupted \
  --output /shared/study/run
```

## Kubernetes Indexed Job

Set `completionMode: Indexed`, mount one ReadWriteMany volume at `/shared`, and
pass the completion index explicitly:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: reva-study
spec:
  completions: 8
  parallelism: 8
  completionMode: Indexed
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: worker
          image: your-registry/reva:locked
          command: ["reva"]
          args:
            - --frozen-plan
            - /shared/study/campaign-plan.json
            - --execute-registry
            - --shard-index
            - $(JOB_COMPLETION_INDEX)
            - --shard-count
            - "8"
            - --worker-id
            - $(JOB_NAME)-$(JOB_COMPLETION_INDEX)
            - --recover-interrupted
            - --output
            - /shared/study/run
          env:
            - name: JOB_COMPLETION_INDEX
              valueFrom:
                fieldRef:
                  fieldPath: metadata.annotations['batch.kubernetes.io/job-completion-index']
            - name: JOB_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            runAsUser: 10001
```

After all tasks finish, audit the complete directory:

```bash
uv run --locked python -m reva.cli \
  --audit-output /shared/study/run
```
