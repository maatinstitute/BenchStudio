# Resource-aware execution preflight (research preview)

BenchStudio can now reject declared memory footprints that cannot fit a worker **before**
constructing either a policy or a simulator in `CampaignExecutor`. This is a
conservative admission check for the existing campaign scheduler, not a new
physics engine, a tensor offloader, or a general GPU memory allocator.

## Inspect hardware

`uv run --locked python -m benchstudio.cli --readiness` reports simulator/model dependencies and
adds a `hardware` object. The zero-dependency probe reads Linux MemAvailable,
respects cgroup v2 `memory.max`/`memory.current` when present, and attempts to
read NVIDIA GPU free/total memory via `nvidia-smi`. On other systems, available
RAM can be unknown. A request that needs unknown capacity is rejected rather
than assumed to fit. NVIDIA telemetry does not detect non-NVIDIA GPUs.

## Freeze an explicit estimate into a campaign

Add the following to the existing `benchstudio.campaign.v1` specification:

```json
{
  "execution": {
    "resource_request": {
      "host_memory_bytes": 2147483648,
      "gpu_memory_bytes": 4294967296,
      "gpu_index": 0
    }
  }
}
```

The example shows only the `execution` section; the full campaign still needs
`experiment`, `task`, `environments`, and `evaluation`. The estimates include
**all additional per-worker allocations** (model, simulator, cameras, buffers,
and subprocesses), not just checkpoint weights. All values are integer bytes.
`gpu_index` is optional; it only selects the device for capacity checking and
**does not bind** CUDA, `CUDA_VISIBLE_DEVICES`, or the simulator to that device.
The caller must ensure the runtime uses the reported device, or pin the index
explicitly. There is no implicit physics, model, image, or CPU fallback.

The requested footprint is checked against a point-in-time hardware snapshot.
For `run_parallel(N)`, declared per-worker RAM/VRAM capacity bounds N before
launching workers. Capacity is not reserved or coordinated across independent
BenchStudio processes. Hardware may change between admission and allocation;
OOM remains possible. `ResourcePlan.to_dict()` explicitly records this limit.
The same preflight evidence is serialized in each run's existing manifest and
bound into its configuration digest and frozen campaign digest.

## Establish a real physics baseline

```bash
uv sync --locked --extra mujoco
uv run --locked python -m benchstudio.cli --readiness
uv run --locked python examples/resource_preflight/benchmark_mujoco.py \
  --episodes 3 --steps 500 --estimated-host-mib 128 \
  --output runs/resource-slider
```

The included MJCF slider is a minimal **real MuJoCo physics** diagnostic. It
runs through `run_episodes`, emits the standard artifacts, and reports
simulation-throughput and process high-water RSS. The completion criterion is
elapsed simulation time, **not manipulation success**; the policy is a frozen
zero-motor control, **not a VLA**. No rendering or GPU acceleration is claimed.
`ru_maxrss` is a process-lifetime high-water gauge (platform-dependent), not
incremental peak memory attributed to one episode. Running a camera-heavy VLA
or an Isaac Lab Newton workload requires separately qualified integrations.

## Next steps (not included)

Actual runtime co-scheduling, GPU/CPU memory reservations, native batched
Isaac Lab/MJWarp execution, measured VRAM peaks, and simulator parity checks
must be implemented and validated separately. A benchmark run on one physics
backend is never evidence that a different backend preserves dynamics.
