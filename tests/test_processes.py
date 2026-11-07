import json
import sys
import pytest
import benchstudio as bs


def test_arguments_and_logs(tmp_path):
    command = bs.ProcessCommand('echo', (sys.executable, '-c', 'import sys; print(sys.argv[1])', '; literal'), tmp_path)
    receipt = command.run(tmp_path / 'logs')
    assert (tmp_path / 'logs/echo.stdout.log').read_text().strip() == '; literal'
    assert json.loads(receipt.read_text())['exit_code'] == 0
    with pytest.raises(FileExistsError):
        command.run(tmp_path / 'logs')


def test_failure_preserves_output(tmp_path):
    command = bs.ProcessCommand('bad', (sys.executable, '-c', 'print("before failure"); raise SystemExit(7)'), tmp_path)
    with pytest.raises(bs.ProcessFailure, match='exited 7'):
        command.run(tmp_path)
    assert json.loads((tmp_path / 'bad.receipt.json').read_text())['exit_code'] == 7


def test_service_cleanup_even_if_client_fails(tmp_path):
    ready_file = tmp_path / 'ready'
    command = bs.ProcessCommand('service', (sys.executable, '-c',
        'from pathlib import Path; import time; Path("ready").touch(); time.sleep(60)'), tmp_path)
    process = None
    with pytest.raises(RuntimeError, match='client failed'):
        with command.service(tmp_path / 'logs', ready=ready_file.exists, startup_timeout=5) as process:
            raise RuntimeError('client failed')
    assert process.poll() is not None
    assert (tmp_path / 'logs/service.receipt.json').exists()


def test_timeout_and_dead_service(tmp_path):
    command = bs.ProcessCommand('slow', (sys.executable, '-c', 'import time; time.sleep(60)'), tmp_path, timeout=0.1)
    with pytest.raises(bs.ProcessFailure, match='timed out'):
        command.run(tmp_path)
    command = bs.ProcessCommand('dead', (sys.executable, '-c', 'raise SystemExit(3)'), tmp_path)
    with pytest.raises(bs.ProcessFailure, match='before readiness'):
        with command.service(tmp_path, ready=lambda: False, startup_timeout=5):
            pytest.fail('client must not start')


def test_command_timeout_still_applies_when_monitoring_service(tmp_path):
    class Alive:
        def poll(self):
            return None
    command = bs.ProcessCommand('dependent', (sys.executable, '-c', 'import time; time.sleep(60)'),
                                tmp_path, timeout=0.1)
    with pytest.raises(bs.ProcessFailure, match='timed out'):
        command.run(tmp_path, required_service=Alive())
    assert json.loads((tmp_path / 'dependent.receipt.json').read_text())['reason'] == 'ProcessFailure'
