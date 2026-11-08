import ast
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import venv

import unittest
import tempfile
import os
from unittest.mock import patch
import benchstudio as bs
from benchstudio.preparation import _IMPORT_PROBE
from benchstudio.source_snapshot import verify_source_snapshot


def package(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    (root / "main.py").write_text('from pathlib import Path; Path("executed").touch()')
    (root / "helper.py").write_text('VALUE = 1')
    return bs.SourcePackage.from_directory(root, files=["main.py", "helper.py"])


class PreparationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_verified_run_and_retained_receipt(self):
        tmp_path = self.root
        source = package(tmp_path)
        receipt = source.run("main.py", log_dir=tmp_path / "logs")
        assert (source.root / "executed").exists()
        assert json.loads(receipt.read_text())["exit_code"] == 0
        report = json.loads((tmp_path / "logs/source-run.sources.json").read_text())
        assert report["valid"] and report["checked_files"] == 2
        with self.assertRaises(FileExistsError):
            source.run("main.py", log_dir=tmp_path / "logs")


    def test_modified_dependency_refuses_before_spawning(self):
        tmp_path = self.root
        change = "modified"
        source = package(tmp_path)
        helper = source.root / "helper.py"
        if change == "missing":
            helper.unlink()
        else:
            helper.write_text('raise RuntimeError("must not import")')
        with self.assertRaises(bs.SourceVerificationError):
            source.run("main.py", log_dir=tmp_path / "logs")
        assert not (source.root / "executed").exists()
        assert not (tmp_path / "logs").exists()


    def test_missing_dependency_refuses_before_spawning(self):
        source = package(self.root)
        (source.root / "helper.py").unlink()
        with self.assertRaises(bs.SourceVerificationError):
            source.run("main.py", log_dir=self.root / "logs")
        assert not (source.root / "executed").exists()

    def test_source_timeout_retains_exit_receipt(self):
        root = self.root / "sources"
        root.mkdir()
        (root / "main.py").write_text("import time; time.sleep(60)")
        source = bs.SourcePackage.from_directory(root, files=["main.py"])
        with self.assertRaises(bs.ProcessFailure):
            source.run("main.py", log_dir=self.root / "logs", timeout=0.05)
        receipt = json.loads((self.root / "logs/source-run.receipt.json").read_text())
        assert receipt["exit_code"] != 0
        assert receipt["reason"] == "ProcessFailure"

    def test_entry_must_be_declared_and_paths_cannot_escape(self):
        tmp_path = self.root
        source = package(tmp_path)
        with self.assertRaises(ValueError):
            source.run("other.py", log_dir=tmp_path / "logs")
        for bad in ("../main.py", "/main.py", "a/../main.py", "./main.py", "a\\main.py"):
            with self.assertRaises(ValueError):
                bs.SourcePackage(source.root, {bad: "a" * 64})
        outside = tmp_path / "outside.py"
        outside.write_text("raise RuntimeError")
        (source.root / "linked.py").symlink_to(outside)
        with self.assertRaises(ValueError):
            bs.SourcePackage.from_directory(source.root, files=["linked.py"])


    def test_manifest_compatibility_and_existing_snapshot_verifier(self):
        tmp_path = self.root
        source = package(tmp_path)
        manifest = tmp_path / "manifest.json"
        for document in ({"schema": "benchstudio_source_snapshot_v1", "files": dict(source.files)},
                         {"all_files_sha256": dict(source.files), "bound": {"ignored": "x"}}):
            manifest.write_text(json.dumps(document))
            imported = bs.SourcePackage.from_manifest(manifest, root=source.root)
            assert imported.verify()["valid"]
        manifest.write_text(json.dumps({"schema": "benchstudio_source_snapshot_v1",
                                        "files": dict(source.files), "commit": "pinned"}))
        assert verify_source_snapshot(manifest, source.root)["commit"] == "pinned"
        manifest.write_text('{"schema": "unexpected", "files": {}}')
        with self.assertRaises(ValueError):
            bs.SourcePackage.from_manifest(manifest, root=source.root)


    def test_deterministic_source_archive_roundtrip(self):
        tmp_path = self.root
        source = package(tmp_path)
        one, two = tmp_path / "one.tar.gz", tmp_path / "two.tar.gz"
        digest = source.archive(one)
        (source.root / "main.py").touch()
        assert source.archive(two) == digest
        assert one.read_bytes() == two.read_bytes()
        assert hashlib.sha256(one.read_bytes()).hexdigest() == digest
        with tarfile.open(one) as archive:
            manifest = json.load(archive.extractfile("SOURCE_MANIFEST.json"))
            for name, expected in manifest["files"].items():
                assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == expected
        with self.assertRaises(FileExistsError):
            source.archive(one)
        assert not (source.root / "executed").exists()


    def test_archive_refuses_tampering_and_manifest_is_immutable(self):
        tmp_path = self.root
        source = package(tmp_path)
        with self.assertRaises(TypeError):
            source.files["helper.py"] = "a" * 64
        (source.root / "helper.py").write_text("changed")
        with self.assertRaises(bs.SourceVerificationError):
            source.archive(tmp_path / "bad.tar.gz")
        assert not (tmp_path / "bad.tar.gz").exists()


    def test_imports_ignore_cwd_and_pythonpath_shadow(self):
        tmp_path = self.root
        (tmp_path / "profile.py").write_text('raise RuntimeError("shadow module")')
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(tmp_path)
        env_patch = patch.dict(os.environ, {"PYTHONPATH": str(tmp_path)})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        result = bs.check_imports("cProfile", "json", log_dir=tmp_path / "logs")
        assert result["ok"]
        assert result["executable"] == sys.executable
        assert all(str(tmp_path) not in item["origin"] for item in result["imports"])
        assert not (tmp_path / "e0-registry").exists()


    def test_missing_import_is_failure_with_report_and_nonzero_exit(self):
        tmp_path = self.root
        with self.assertRaises(bs.ProcessFailure):
            bs.check_imports("benchstudio_nonexistent_native_dependency", log_dir=tmp_path / "logs")
        report = json.loads((tmp_path / "logs/imports.json").read_text())
        assert report["ok"] is False
        assert "ModuleNotFoundError" in report["imports"][0]["error"]
        assert json.loads((tmp_path / "logs/imports.receipt.json").read_text())["exit_code"] == 1


    def test_native_import_exit_zero_is_still_failure(self):
        tmp_path = self.root
        native = tmp_path / "native"
        venv.EnvBuilder(with_pip=False).create(native)
        python = native / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        site = next(native.glob("Lib/site-packages"), None) or next(native.glob("lib/python*/site-packages"))
        (site / "synthetic_exit.py").write_text('raise SystemExit(0)')
        with self.assertRaises(bs.ProcessFailure):
            bs.check_imports("synthetic_exit", python=str(python), log_dir=tmp_path / "logs")
        report = json.loads((tmp_path / "logs/imports.json").read_text())
        assert report["ok"] is False and "SystemExit" in report["imports"][0]["error"]


    def test_worker_is_python38_syntax_and_module_names_are_validated(self):
        tmp_path = self.root
        ast.parse(_IMPORT_PROBE, feature_version=(3, 8))
        with self.assertRaises(ValueError):
            bs.check_imports("import os; os.system('bad')", log_dir=tmp_path / "logs")
        assert not (tmp_path / "logs").exists()

if __name__ == "__main__":
    unittest.main()
