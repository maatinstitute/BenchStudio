"""Pure-Python hardware admission tests; no GPU or MuJoCo required."""

import json

import pytest

from benchstudio.campaigns import CampaignExecutor, CampaignPlanner, compile_campaign_spec
from benchstudio.hardware import (
    GPUMemory,
    HardwareSnapshot,
    ResourceAdmissionError,
    ResourceRequest,
    _parse_meminfo,
    _parse_nvidia_smi,
    plan_execution_resources,
)
from benchstudio.mock import MockPolicy, MockSimulator


def _hardware(*, ram=256, gpu=96):
    mib = 1024 * 1024
    return HardwareSnapshot(
        logical_cpus=8,
        total_ram_bytes=512 * mib,
        available_ram_bytes=ram * mib,
        gpus=(GPUMemory(0, 256 * mib, gpu * mib),),
        gpu_probe_status="fixture",
    )


def test_resource_plan_selects_gpu_and_capacity_without_changing_backend():
    mib = 1024 * 1024
    plan = plan_execution_resources(
        ResourceRequest(host_memory_bytes=100 * mib, gpu_memory_bytes=40 * mib),
        _hardware(),
    )
    assert plan.selected_gpu_index == 0
    assert plan.max_parallel_workers == 2
    assert plan.to_dict()["status"] == "admitted_estimate"
    assert "no memory is reserved" in plan.to_dict()["note"]


def test_resource_plan_has_no_cpu_fallback_for_gpu_request():
    with pytest.raises(ResourceAdmissionError, match="VRAM"):
        plan_execution_resources(ResourceRequest(gpu_memory_bytes=100 * 1024 * 1024), _hardware())


def test_resource_plan_rejects_undetectable_memory():
    snapshot = HardwareSnapshot(4, None, None)
    with pytest.raises(ResourceAdmissionError, match="unknown"):
        plan_execution_resources(ResourceRequest(host_memory_bytes=1), snapshot)


@pytest.mark.parametrize(
    "value",
    [
        {"host_memory_bytes": True},
        {"gpu_index": 0},
        {"gpu_memory_bytes": -1},
        {"gpu_memory_bytes": 1.5},
        {"unknown": 1},
    ],
)
def test_resource_request_rejects_unsafe_frozen_values(value):
    with pytest.raises(ValueError):
        ResourceRequest.from_mapping(value)


def test_hardware_parsers_use_bytes_and_reject_bad_gpu_data():
    assert _parse_meminfo("MemTotal: 1000 kB\nMemAvailable: 250 kB\n") == (1024000, 256000)
    assert _parse_nvidia_smi("0, 8192, 4096\n")[0].available_bytes == 4096 * 1024 * 1024
    with pytest.raises(ValueError):
        _parse_nvidia_smi("0, 8192 MiB, N/A\n")


def _plan_with_request(request):
    return CampaignPlanner(
        run_id="resource-smoke",
        scenario_id="mock-task",
        conditions=[{"denoising_steps": 2, "action_prefix": 1}],
        seeds=[1],
        protocol={"X": {"resource_request": request}},
    ).freeze()


def test_preflight_rejects_before_constructing_policy_or_simulator(tmp_path):
    calls = []
    factory = lambda _: calls.append("constructed")  # noqa: E731
    with pytest.raises(ResourceAdmissionError):
        CampaignExecutor(
            _plan_with_request({"host_memory_bytes": 500 * 1024 * 1024}),
            tmp_path / "run",
            policy_factory=factory,
            simulator_factory=factory,
            hardware_snapshot=_hardware(),
        )
    assert calls == []
    assert not (tmp_path / "run").exists()


def test_preflight_is_frozen_into_existing_run_manifest(tmp_path):
    exe = CampaignExecutor(
        _plan_with_request({"host_memory_bytes": 100 * 1024 * 1024}),
        tmp_path / "run",
        policy_factory=lambda _: MockPolicy(),
        simulator_factory=lambda _: MockSimulator(),
        hardware_snapshot=_hardware(),
    )
    summary = exe.run()
    assert summary.committed_attempt_ids == ("attempt-000000",)
    record = json.loads(
        (tmp_path / "run" / "attempts" / "attempt-000000" / "manifest.json").read_text()
    )
    preflight = record["config"]["resource_preflight"]
    assert preflight["schema"] == "benchstudio.resource_preflight.v1"
    assert preflight["hardware"]["logical_cpus"] == 8
    assert exe.audit().evidence_verified


def test_parallel_workers_must_fit_declared_capacity(tmp_path):
    exe = CampaignExecutor(
        _plan_with_request({"gpu_memory_bytes": 60 * 1024 * 1024}),
        tmp_path / "run",
        policy_factory=lambda _: MockPolicy(),
        simulator_factory=lambda _: MockSimulator(),
        hardware_snapshot=_hardware(),
    )
    with pytest.raises(ValueError, match="resource preflight capacity"):
        exe.run_parallel(2)


def test_campaign_compiler_validates_resource_request():
    spec = {
        "schema": "benchstudio.campaign.v1",
        "experiment": {"name": "resource"},
        "task": {"task_id": "task"},
        "environments": [{"id": "sim", "kind": "simulator"}],
        "evaluation": {"seeds": [1], "paired": True, "conditions": [{"id": "test"}]},
        "execution": {"resource_request": {"host_memory_bytes": 1}},
    }
    plan = compile_campaign_spec(spec)
    assert plan.protocol["X"]["resource_request"]["host_memory_bytes"] == 1
    spec["execution"]["resource_request"]["gpu_memory_bytes"] = True
    with pytest.raises(ValueError):
        compile_campaign_spec(spec)
