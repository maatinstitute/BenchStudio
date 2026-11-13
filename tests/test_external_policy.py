from __future__ import annotations

import sys

import pytest

from ival.contracts import Observation, Timestamp
from ival.external_policy import (
    ExternalCommandPolicy,
    PersistentExternalCommandPolicy,
)


def _command(script: str) -> tuple[str, ...]:
    return (sys.executable, "-c", script)


def test_external_command_policy_uses_strict_json_boundary():
    policy = ExternalCommandPolicy(
        _command(
            "import json,sys; request=json.load(sys.stdin); "
            "print(json.dumps({'actions':[request['observation']['sequence']],"
            "'metadata':{'seed':request['seed']}}))"
        )
    )
    policy.reset(seed=7)
    result = policy.predict(
        Observation(
            sequence=3,
            sim_time_s=0.2,
            payload={"joint": [1, 2]},
            source_timestamp=Timestamp(200, "sim_time"),
            received_monotonic_ns=100,
        ),
        denoising_steps=2,
    )
    assert result.actions == (3,)
    assert result.metadata == {"seed": 7}


def test_external_command_policy_reports_process_failures():
    policy = ExternalCommandPolicy(_command("import sys; sys.stderr.write('bad'); sys.exit(3)"))
    policy.reset(seed=1)
    with pytest.raises(RuntimeError, match="code 3"):
        policy.predict(Observation(0, 0.0), denoising_steps=None)


def test_external_command_policy_rejects_malformed_responses():
    policy = ExternalCommandPolicy(_command("print('{}')"))
    policy.reset(seed=1)
    with pytest.raises(ValueError, match="actions array"):
        policy.predict(Observation(0, 0.0), denoising_steps=None)


def test_persistent_external_command_policy_keeps_runtime_alive():
    policy = PersistentExternalCommandPolicy(
        _command(
            "import json,sys; "
            "[print(json.dumps({'status':'ok'}), flush=True) if r['operation']=='reset' "
            "else print(json.dumps({'actions':[r['observation']['sequence']],"
            "'metadata':{'seed':r['seed']}}), flush=True) if r['operation']=='predict' "
            "else print(json.dumps({'status':'closed'}), flush=True) "
            "for r in map(json.loads,sys.stdin)]"
        )
    )
    policy.reset(seed=11)
    assert policy.predict(Observation(4, 0.4), denoising_steps=3).actions == (4,)
    assert policy.predict(Observation(5, 0.5), denoising_steps=3).metadata == {"seed": 11}
    process = policy._process
    policy.close()
    assert process is not None and process.poll() is not None


@pytest.mark.parametrize("seed", [True, 1.5])
def test_external_policies_reject_non_integer_seeds(seed):
    with pytest.raises(ValueError, match="seed must be an integer"):
        ExternalCommandPolicy(_command("print('{}')")).reset(seed=seed)
    with pytest.raises(ValueError, match="seed must be an integer"):
        PersistentExternalCommandPolicy(_command("print('{}')")).reset(seed=seed)


def test_persistent_external_policy_timeout_detaches_process():
    policy = PersistentExternalCommandPolicy(_command("import time; time.sleep(1)"), timeout_s=0.05)
    with pytest.raises(TimeoutError):
        policy.reset(seed=1)
    assert policy._process is None
