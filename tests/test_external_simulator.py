from __future__ import annotations

import sys

import pytest

from reva.external_simulator import ExternalCommandSimulator, _observation


def test_external_command_simulator_preserves_reset_step_state():
    script = (
        "import json,sys; step=0;\n"
        "for line in sys.stdin:\n"
        " request=json.loads(line); op=request['operation'];\n"
        " if op=='reset': step=0;\n"
        " if op=='step': step+=1;\n"
        " if op=='close': break;\n"
        " print(json.dumps({'observation':{'sequence':step,'sim_time_s':step/10,'payload':{}},"
        "'done':step>=1,'success':step>=1}), flush=True)\n"
    )
    simulator = ExternalCommandSimulator((sys.executable, "-u", "-c", script))
    try:
        initial = simulator.reset(seed=3)
        assert initial.sequence == 0
        assert simulator.is_done() is False
        next_observation = simulator.step(1)
        assert next_observation.sequence == 1
        assert simulator.is_done() is True
        assert simulator.is_success() is True
    finally:
        simulator.close()


def test_external_command_simulator_is_registered_and_ready():
    from reva.adapters import default_registry

    registry = default_registry(discover_external=False)
    readiness = registry.readiness("external_command")
    assert readiness["ready"] is True
    assert readiness["capabilities"]["closed_loop"] is True


@pytest.mark.parametrize(
    "response",
    [
        {"observation": {"sequence": "0", "sim_time_s": 0.0, "payload": {}}},
        {"observation": {"sequence": 0, "sim_time_s": "0.0", "payload": {}}},
        {"observation": {"sequence": 0, "sim_time_s": 0.0, "payload": []}},
        {
            "observation": {
                "sequence": 0,
                "sim_time_s": 0.0,
                "payload": {},
                "source_timestamp": {"value_ns": "0", "domain": "sim_time"},
            }
        },
        {
            "observation": {
                "sequence": 0,
                "sim_time_s": 0.0,
                "payload": {},
                "source_timestamp": {"value_ns": 0, "domain": "unknown_clock"},
            }
        },
    ],
)
def test_external_simulator_rejects_coerced_observation_fields(response):
    with pytest.raises(ValueError, match="observation"):
        _observation(response)


def test_external_simulator_reset_clears_terminal_state_when_flags_are_omitted():
    script = (
        "import json,sys; reset_count=0;\n"
        "for line in sys.stdin:\n"
        " request=json.loads(line); op=request['operation'];\n"
        " if op=='reset':\n"
        "  reset_count+=1; response={'observation':{'sequence':0,'sim_time_s':0.0,'payload':{}}};\n"
        " elif op=='step': response={'observation':{'sequence':1,'sim_time_s':0.1,"
        "'payload':{}},'done':True,'success':True};\n"
        " elif op=='close': break\n"
        " else: response={'observation':{'sequence':0,'sim_time_s':0.0,'payload':{}}}\n"
        " print(json.dumps(response),flush=True)\n"
    )
    simulator = ExternalCommandSimulator((sys.executable, "-u", "-c", script))
    try:
        simulator.reset(seed=1)
        simulator.step(1)
        assert simulator.is_done() is True
        simulator.reset(seed=2)
        assert simulator.is_done() is False
        assert simulator.is_success() is False
    finally:
        simulator.close()


def test_external_simulator_timeout_detaches_process():
    script = "import time; time.sleep(1)"
    simulator = ExternalCommandSimulator((sys.executable, "-u", "-c", script), timeout_s=0.05)
    with pytest.raises(TimeoutError):
        simulator.reset(seed=1)
    assert simulator._process is None
