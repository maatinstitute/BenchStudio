import sys
import pytest
import benchstudio as bs


def test_structured_nonzero_result_preserves_streams_and_exit(tmp_path):
    command = bs.ProcessCommand("scene", (sys.executable, "-c",
        'import sys; print("stdout"); print("stderr", file=sys.stderr); sys.exit(7)'), tmp_path)
    result = command.execute(tmp_path / "logs", check=False)
    assert isinstance(result, bs.ProcessResult)
    assert result.returncode == 7 and result.duration >= 0
    assert result.stdout_path.read_text().strip() == "stdout"
    assert result.stderr_path.read_text().strip() == "stderr"
    assert result.receipt_path.exists()


def test_raised_failure_has_same_typed_receipt(tmp_path):
    command = bs.ProcessCommand("failed", (sys.executable, "-c", "raise SystemExit(9)"), tmp_path)
    with pytest.raises(bs.ProcessFailure) as caught:
        command.execute(tmp_path)
    assert caught.value.result.returncode == 9
    assert caught.value.result.receipt_path.exists()


def test_timeout_never_becomes_success_with_check_false(tmp_path):
    command = bs.ProcessCommand("slow", (sys.executable, "-c", "import time; time.sleep(60)"),
                                tmp_path, timeout=.05)
    with pytest.raises(bs.ProcessFailure) as caught:
        command.execute(tmp_path, check=False)
    assert caught.value.result.returncode != 0
