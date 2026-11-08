import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


def fixture(tmp_path):
    root = tmp_path / "staged source"
    root.mkdir()
    script = root / "native.py"
    script.write_text('import json,sys; from pathlib import Path; '
                      'Path("received.json").write_text(json.dumps(sys.argv[1:]))')
    manifest = tmp_path / "STAGE_MANIFEST.json"
    manifest.write_text(json.dumps({"all_files_sha256": {
        "native.py": hashlib.sha256(script.read_bytes()).hexdigest()}}))
    return root, script, manifest


def command(*args):
    return subprocess.run([sys.executable, "-m", "benchstudio", *map(str, args)],
                          capture_output=True, text=True, timeout=20)


def test_single_command_checks_imports_then_forwards_literal_native_arguments(tmp_path):
    root, _, manifest = fixture(tmp_path)
    result = command("run", "--manifest", manifest, "--root", root,
                     "--python", sys.executable, "--entrypoint", "native.py",
                     "--log-dir", tmp_path / "logs", "--check-import", "json",
                     "--", "--scope", "existing scope", "; literal")
    assert result.returncode == 0, result.stderr
    assert json.loads((root / "received.json").read_text()) == [
        "--scope", "existing scope", "; literal"]
    assert json.loads((tmp_path / "logs/imports/imports.json").read_text())["ok"]
    assert (tmp_path / "logs/source-run.sources.json").exists()


@pytest.mark.parametrize("failure", ["hash", "import"])
def test_prelaunch_failure_never_starts_native_entry(tmp_path, failure):
    root, script, manifest = fixture(tmp_path)
    if failure == "hash":
        script.write_text(script.read_text() + "\n# changed")
    result = command("run", "--manifest", manifest, "--root", root,
                     "--python", sys.executable, "--entrypoint", "native.py",
                     "--log-dir", tmp_path / "logs", "--check-import",
                     "missing_native_module_for_synthetic_test")
    assert result.returncode != 0
    assert not (root / "received.json").exists()
    assert not (tmp_path / "logs/source-run.receipt.json").exists()
    if failure == "hash":
        assert not (tmp_path / "logs").exists()


def test_verify_and_archive_need_no_native_interpreter(tmp_path):
    root, _, manifest = fixture(tmp_path)
    result = command("verify", "--manifest", manifest, "--root", root)
    assert result.returncode == 0 and json.loads(result.stdout)["valid"]
    result = command("package", "--manifest", manifest, "--root", root,
                     "--output", tmp_path / "sources.tar.gz")
    assert result.returncode == 0
    assert json.loads(result.stdout)["sha256"] == hashlib.sha256(
        (tmp_path / "sources.tar.gz").read_bytes()).hexdigest()
    assert not (root / "received.json").exists()


def test_import_only_command_reports_failure_without_native_run(tmp_path):
    result = command("doctor", "--python", sys.executable,
                     "--log-dir", tmp_path / "logs", "missing_native_module_for_synthetic_test")
    assert result.returncode != 0
    assert json.loads((tmp_path / "logs/imports.json").read_text())["ok"] is False


def test_unified_help_and_evaluation_help_do_not_execute(tmp_path):
    result = command()
    assert result.returncode == 0
    assert all(name in result.stdout for name in (
        "run", "verify", "package", "doctor", "evaluate", "campaign", "replay"
    ))
    result = command("evaluate", "--help")
    assert result.returncode == 0 and "--system" in result.stdout
    result = command("campaign", "--help")
    assert result.returncode == 0 and "benchstudio campaign" in result.stdout
    result = command("replay", "--help")
    assert result.returncode == 0 and "benchstudio replay" in result.stdout


def test_specialist_module_is_not_a_second_cli_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "benchstudio.cli", "--help"],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode != 0
    assert "Use `benchstudio campaign ...`" in result.stderr


def test_source_check_also_protects_services_and_direct_process_context(tmp_path, monkeypatch):
    from benchstudio.preparation import SourcePackage, SourceVerificationError
    from benchstudio.processes import ProcessCommand
    root, script, manifest = fixture(tmp_path)
    sources = SourcePackage.from_manifest(manifest, root=root)
    process = ProcessCommand("example", (sys.executable, str(script)), root, sources=sources)
    script.write_text("changed")
    def forbidden_spawn(*args, **kwargs):
        pytest.fail("a process was started before source verification")
    monkeypatch.setattr("benchstudio.processes.subprocess.Popen", forbidden_spawn)
    for direct in (False, True):
        with pytest.raises(SourceVerificationError):
            manager = process.started(tmp_path / "logs") if direct else process.service(
                tmp_path / "logs", ready=lambda: True)
            with manager:
                pytest.fail("unverified process context entered")
    assert not (tmp_path / "logs").exists()


def test_cli_rechecks_sources_after_requested_import_diagnostic(tmp_path, monkeypatch):
    from benchstudio.preparation_cli import main
    root, script, manifest = fixture(tmp_path)
    def changed_by_import(*args, **kwargs):
        script.write_text("changed")
        return {"ok": True}
    monkeypatch.setattr("benchstudio.preparation_cli.check_imports", changed_by_import)
    code = main(["run", "--manifest", str(manifest), "--root", str(root),
                 "--python", sys.executable, "--entrypoint", "native.py",
                 "--log-dir", str(tmp_path / "logs"), "--check-import", "json"])
    assert code != 0 and not (root / "received.json").exists()
