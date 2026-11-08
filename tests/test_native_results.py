from types import SimpleNamespace

import pytest

import benchstudio as bs


def test_retained_native_result_reader_is_explicit_and_does_not_run(tmp_path, monkeypatch):
    calls = []
    result = SimpleNamespace(summary=lambda: "native retained metrics")
    factory = SimpleNamespace(open_run=lambda path: calls.append(path) or result)
    monkeypatch.setattr("benchstudio.backend_loading.load_backend", lambda group, name: factory)
    assert bs.open_run(tmp_path, backend="saved-native") is result
    assert calls == [tmp_path]


def test_no_backend_detection_or_fallback_on_corrupt_system_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr("benchstudio.backend_loading.load_backend", lambda *args: pytest.fail("fallback"))
    with pytest.raises((ValueError, FileNotFoundError)):
        bs.open_run(tmp_path)


@pytest.mark.parametrize("factory", [SimpleNamespace(),
    SimpleNamespace(open_run=lambda path: object())])
def test_native_reader_contract_must_be_supported(tmp_path, monkeypatch, factory):
    monkeypatch.setattr("benchstudio.backend_loading.load_backend", lambda *args: factory)
    with pytest.raises(TypeError):
        bs.open_run(tmp_path, backend="invalid")


def test_common_check_never_implies_native_qualification():
    report = bs.EvaluationCheck(True, (), 2, "native")
    assert report.technical_ready and report.configuration_valid
    assert not report.native_verified
    assert "unverified" in report.summary()


@pytest.mark.parametrize("flag", ["--output-dir", "--output"])
def test_common_cli_output_aliases_are_read_only_on_check(tmp_path, monkeypatch, flag):
    from benchstudio.commands import main
    system = bs.System.from_callable(lambda x: pytest.fail("runtime executed"), name="s", revision="r")
    benchmark = bs.Benchmark("b", "r", [1], [1], lambda a, b: bs.Score(), "r")
    monkeypatch.setattr(bs.System, "from_backend", lambda *a, **kw: system)
    monkeypatch.setattr(bs.Benchmark, "load", lambda *a, **kw: benchmark)
    assert main(["evaluate", "--system", "s", "--system-revision", "r", "--benchmark", "b",
                 "--benchmark-revision", "r", flag, str(tmp_path / "out"), "--check"]) == 0
    assert not (tmp_path / "out").exists()
