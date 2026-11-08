from types import SimpleNamespace

import pytest
import benchstudio as bs
from benchstudio.commands import main


def test_installed_pipeline_is_constructed_without_execution(monkeypatch):
    calls = []
    backend = SimpleNamespace(check=lambda: "check", run=lambda: calls.append("run"))
    monkeypatch.setattr("benchstudio.backend_loading.metadata.entry_points", lambda **kw: [
        SimpleNamespace(load=lambda: lambda **options: backend)])
    assert bs.pipeline("installed-study") is backend
    assert calls == []


@pytest.mark.parametrize("successful", [False, True])
def test_recipe_cli_preserves_batch_failure(monkeypatch, successful):
    class Factory:
        def add_cli_args(self, parser):
            pass
        def options_from_args(self, args):
            return {}
        def __call__(self):
            return SimpleNamespace(check=lambda: None, run=lambda: SimpleNamespace(
                successful=successful, summary=lambda: "native batch"))
    monkeypatch.setattr("benchstudio.backend_loading.metadata.entry_points", lambda **kw: [
        SimpleNamespace(load=lambda: Factory())])
    assert main(["evaluate", "--recipe", "batch"]) == (0 if successful else 1)


def test_invalid_installed_pipeline_contract_fails(monkeypatch):
    monkeypatch.setattr("benchstudio.backend_loading.metadata.entry_points", lambda **kw: [
        SimpleNamespace(load=lambda: lambda **options: object())])
    with pytest.raises(TypeError, match="check.*run"):
        bs.pipeline("broken")


@pytest.mark.parametrize("authorized", [False, True])
def test_recipe_cli_check_never_calls_run(monkeypatch, authorized):
    calls = []
    report = bs.RefinementPreparation({"model": {"offline_inputs_complete": True, "issues": [],
        "execution_authorized": authorized}})
    class Factory:
        def add_cli_args(self, parser):
            parser.add_argument("--revision", required=True)
        def options_from_args(self, args):
            return {"revision": args.revision}
        def __call__(self, **options):
            assert options == {"revision": "pinned"}
            return SimpleNamespace(check=lambda: report, run=lambda: calls.append("run"))
    monkeypatch.setattr("benchstudio.backend_loading.metadata.entry_points", lambda **kw: [
        SimpleNamespace(load=lambda: Factory())])
    assert main(["evaluate", "--recipe", "study", "--revision", "pinned", "--check"]) == (0 if authorized else 1)
    assert calls == []
