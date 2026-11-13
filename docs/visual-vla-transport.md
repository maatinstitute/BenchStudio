# Local visual VLA execution (research preview)

IVal's existing `MujocoSimulator` can optionally render a named camera.
Each `Observation` contains the original joint state plus
`payload["images"]["front"]` as a `uint8` H×W×3 array. Rendering is **disabled
by default**. The caller must choose a camera, size, graphics backend and
checkpoint-specific observation mapping; IVal does **not** infer LeRobot
normalization, state vectors or task success criteria.

## Same-host mmap transport

An external model process can opt in to `tensor_transport="mmap"` on
`PersistentExternalCommandPolicy` (also the registered `smolvla` model bridge).
Large numeric numpy arrays are written once into a private temporary directory
and represented in JSON with a **filename, dtype, shape, byte count, SHA-256**.
The child can use `ival.local_tensors.open_local_tensors(payload, root=...)`
inside an inference call, making `numpy.memmap` views without expanding the
images into JSON lists. The parent removes the temporary files when the call
returns or raises, and removes the directory on `close()`.

- Linux prefers `/dev/shm` (tmpfs). Other platforms may use disk-backed mmap.
  This is **not** GPU shared memory, zero-copy GPU inference or compression.
- The subprocess must be trusted and on the **same host and user**. It receives
  the publisher's private directory through `IVAL_LOCAL_TENSOR_ROOT`.
- `numpy` is required in both processes in mmap mode. The external LeRobot
  environment must also have the lightweight `ival` package installed
  so the reader is not copied or maintained separately.
- Array descriptors are strictly validated, content-digested, size-capped,
  and removed after each request. The model must finish using the arrays
  before responding; it cannot retain the mmap views between requests.
- Existing JSON protocol remains the default; no legacy adapter aliases.
- Camera frames still require a frozen mapping to `policy_batch` with the exact
  checkpoint-specific dtype, layout, normalization, proprioception, and policy
  vocabulary. Sending arbitrary camera pixels to SmolVLA is not valid.

## Explicit device selection

Set `device="cpu"`, `device="cuda:0"` or `device="mps"` in the policy
bridge. It forwards `IVAL_LEROBOT_DEVICE`; the LeRobot subprocess
validates availability, calls `policy.to(device)` and fails instead of silently
falling back to CPU. GPU indices inside a subprocess may be remapped by
`CUDA_VISIBLE_DEVICES`; the operator must ensure the resource preflight and
model process refer to the same physical accelerator.

## Scientific acceptance / not yet demonstrated

The checked-in tests cover array integrity, cleanup, a persistent cross-process
policy call using real NumPy images, and the MuJoCo RGB renderer where the
operating system provides a usable OpenGL context. These tests do **not**
exercise a trained SmolVLA checkpoint or a real manipulation outcome.

The next external qualification requires an independently frozen checkpoint,
MuJoCo task/robot/controller, camera calibration, the real LeRobot preprocessing
and normalization contracts, and a trusted success predicate. Run matched JSON
vs mmap (if feasible) with the same inputs. Measure peak host/VRAM across
model loading, per-step transfer overhead, p95 inference latency, task success,
and observation/action parity. Until those are available, do not claim that
8 GB VRAM execution, lower peak memory, or checkpoint evaluation has been
achieved. A faster transport does not itself reduce model-weight residency.

## Execute a real checkpoint (only with qualified assets)

`examples/resource_preflight/run_visual_smolvla.py` is an optional example
that uses the normal IVal `run_episodes` runner with a real MuJoCo
scene and the existing LeRobot SmolVLA external process. It requires:

- a local immutable checkpoint and externally validated digest;
- a camera-equipped MuJoCo MJCF scene;
- a versioned `module:function` to convert raw simulator state and RGB to the
  checkpoint's expected `policy_batch` representation; and
- a benchmark-owned `module:function` success predicate (model, data).

Both callback source digests and the scene digest are retained in the normal
run manifest. The example rejects incomplete assets and does not use a
synthetic `success=True` fallback. On a Linux machine with the external LeRobot
environment and IVal both installed:

```bash
uv run --locked python examples/resource_preflight/run_visual_smolvla.py \
  --scene /path/to/scene.xml --camera-name front \
  --checkpoint /path/to/pinned/smolvla \
  --checkpoint-sha256 <independently-reviewed-64-hex-digest> \
  --map-input my_qualified_mapping:make_policy_batch \
  --success-fn my_qualified_scoring:is_success \
  --device cuda:0 --estimated-host-mib 4096 --estimated-gpu-mib 8192 \
  --output runs/visual-smolvla
```

The script is a runtime entrypoint, **not** a trained checkpoint, compatible
robot/controller bundle, or proof of evaluation quality. Its policy output
must already be in the simulator's actuator command representation; otherwise
the normal action validator or MuJoCo adapter must reject it. Use the external
benchmark's authoritative success checker, not a heuristic surrogate.