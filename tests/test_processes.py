import json
import sys
import pytest
import benchstudio as bs
from benchstudio.processes import ProcessCommand, ProcessFailure


def test_arguments_and_logs(tmp_path):
    command = ProcessCommand('echo', (sys.executable, '-c', 'import sys; print(sys.argv[1])', '; literal'), tmp_path)
    receipt = command.execute(tmp_path / 'logs').receipt_path
    assert (tmp_path / 'logs/echo.stdout.log').read_text().strip() == '; literal'
    assert json.loads(receipt.read_text())['exit_code'] == 0
    with pytest.raises(FileExistsError):
        command.execute(tmp_path / 'logs').receipt_path


def test_failure_preserves_output(tmp_path):
    command = ProcessCommand('bad', (sys.executable, '-c', 'print("before failure"); raise SystemExit(7)'), tmp_path)
    with pytest.raises(ProcessFailure, match='exited 7'):
        command.execute(tmp_path).receipt_path
    assert json.loads((tmp_path / 'bad.receipt.json').read_text())['exit_code'] == 7


def test_service_cleanup_even_if_client_fails(tmp_path):
    ready_file = tmp_path / 'ready'
    command = ProcessCommand('service', (sys.executable, '-c',
        'from pathlib import Path; import time; Path("ready").touch(); time.sleep(60)'), tmp_path)
    process = None
    with pytest.raises(RuntimeError, match='client failed'):
        with command.service(tmp_path / 'logs', ready=ready_file.exists, startup_timeout=5) as process:
            raise RuntimeError('client failed')
    assert process.poll() is not None
    assert (tmp_path / 'logs/service.receipt.json').exists()


def test_timeout_and_dead_service(tmp_path):
    command = ProcessCommand('slow', (sys.executable, '-c', 'import time; time.sleep(60)'), tmp_path, timeout=0.1)
    with pytest.raises(ProcessFailure, match='timed out'):
        command.execute(tmp_path).receipt_path
    command = ProcessCommand('dead', (sys.executable, '-c', 'raise SystemExit(3)'), tmp_path)
    with pytest.raises(ProcessFailure, match='before readiness'):
        with command.service(tmp_path, ready=lambda: False, startup_timeout=5):
            pytest.fail('client must not start')


def test_command_timeout_still_applies_when_monitoring_service(tmp_path):
    class Alive:
        def poll(self):
            return None
    command = ProcessCommand('dependent', (sys.executable, '-c', 'import time; time.sleep(60)'),
                                tmp_path, timeout=0.1)
    with pytest.raises(ProcessFailure, match='timed out'):
        command.execute(tmp_path, required_service=Alive())
    assert json.loads((tmp_path / 'dependent.receipt.json').read_text())['reason'] == 'ProcessFailure'
