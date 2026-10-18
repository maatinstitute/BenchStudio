from __future__ import annotations

import sys

from benchstudio.external_simulator import ExternalCommandSimulator


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
    from benchstudio.adapters import default_registry

    registry = default_registry(discover_external=False)
    readiness = registry.readiness("external_command")
    assert readiness["ready"] is True
    assert readiness["capabilities"]["closed_loop"] is True
