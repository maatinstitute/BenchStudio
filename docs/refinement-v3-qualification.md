# Refinement/Refresh v3 launch qualification

Enable this guard in a declarative campaign under
`experiment.refinement_v3` (frozen as `P.experiment.refinement_v3`).
The declaration contains:

- `stage: "confirmation"`.
- `model: "pi0.5"` or `model: "smolvla"`.
- `runtime`: lowercase SHA-256 values keyed by `runner`, `checkpoint`,
  `simulator_stack`, `renderer`, `assets` and `normalization`.

Compile and review the plan before authorizing it. Supply a qualification
directory to `--qualification-directory` and obtain the SHA-256 of
`approval.json` directly from the approver for
`--qualification-approval-sha256`. The Python executor takes the same
values as `qualification_directory` and `trusted_approval_sha256`.
The launch check runs before an attempt initializes a policy or simulator.

The directory contains:

- `runtime.json`: the exact runtime identity mapping above, independently
  captured by the deployment tooling from the selected environment before
  launch. BenchStudio compares these observations to the frozen declaration.
  Collecting and verifying live process provenance remains the native launcher’s
  responsibility. An operator-authored copy of the expected mapping is not
  runtime evidence.
- `engineering_preflight.json` and `evaluator.json`, each with
  `"passed": true` and the evidence reviewed by the approver. For π0.5, also
  supply `stock_parity.json` and `g02.json`.
- `approval.json`: `schema` is `benchstudio.refinement_v3_approval.v1`,
  `plan_digest_sha256` is the frozen plan digest, and `evidence` maps each
  required report's stem to the SHA-256 of its exact file bytes. Approve the
  report content independently. The guard verifies the authorization and
  its bindings, rather than rerunning those diagnostic checks.

## Native π0.5 bridge

The guarded executor uses the persistent external policy bridge in synchronous
mode. Each predict request includes a unique `request_id`. The native process
must use its qualified compiled counter for that request and return:

```json
{"actions": [[0.0]], "metadata": {"denoising_attestation": {
  "request_id": "<request_id from predict>",
  "executed_steps": 2
}}}
```

The bridge rejects missing, stale or mismatched attestations before returning
the action chunk. The runner records an instrument failure and the executor
stops the campaign. A recorded incident also blocks resuming the same ledger.
Use a single worker for this protocol. The native OpenPI counter, the LeRobot
and LIBERO qualification fixtures, and v3 paired analysis are separate work.
