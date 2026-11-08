"""Prepare trusted external programs without importing their code in this process."""
from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import tempfile
from types import MappingProxyType
from typing import Iterable, Mapping

from .processes import ProcessCommand, ProcessFailure
from .source_snapshot import verify_source_files


class SourceVerificationError(ValueError):
    """Declared source files do not match the retained package."""


def _relative(path: str) -> str:
    if (not isinstance(path, str) or not path or "\\" in path
            or PurePosixPath(path).is_absolute()
            or any(part in ("", ".", "..") for part in path.split("/"))):
        raise ValueError("source paths must be canonical relative POSIX paths")
    return path


@dataclass(frozen=True)
class SourcePackage:
    """Explicit source files and their digests; verifies again on every run.

    This checks integrity on a trusted host. It neither grants permission nor
    sandboxes Python, validates dependencies, or prevents concurrent file mutation.
    """

    root: Path
    files: Mapping[str, str]

    def __post_init__(self):
        root = Path(self.root).resolve()
        files = dict(self.files)
        if not files:
            raise ValueError("source files must not be empty")
        for name, digest in files.items():
            _relative(name)
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("expected SHA-256 must be 64 lowercase hex characters")
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "files", MappingProxyType(files))

    @classmethod
    def from_directory(cls, root: str | Path, *, files: Iterable[str]) -> SourcePackage:
        """Snapshot explicitly selected files. Selection is not a trust decision."""
        root = Path(root).resolve()
        digests = {}
        for name in files:
            _relative(name)
            path = (root / name).resolve()
            path.relative_to(root)
            digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return cls(root, digests)

    @classmethod
    def from_manifest(cls, path: str | Path, *, root: str | Path) -> SourcePackage:
        """Read a BenchStudio source snapshot or the frozen E0 manifest format.

        The external E0 schema is read-only here. Bound/authorization fields are
        deliberately not interpreted by this generic source verifier.
        """
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("source manifest must be an object")
        if document.get("schema") == "benchstudio_source_snapshot_v1":
            files = document.get("files")
        elif "all_files_sha256" in document and "schema" not in document:
            files = document["all_files_sha256"]
        else:
            raise ValueError("unsupported source manifest")
        if not isinstance(files, dict):
            raise ValueError("source files must be a mapping")
        return cls(Path(root), files)

    def verify(self) -> dict:
        """Return current integrity findings without importing package code."""
        return {**verify_source_files(dict(self.files), self.root),
                "files_sha256": dict(self.files)}

    def _require_verified(self) -> dict:
        report = self.verify()
        if not report["valid"]:
            raise SourceVerificationError("source verification failed: " + repr(report["mismatches"]))
        return report

    def run(self, entrypoint: str, *, log_dir: str | Path, python: str = sys.executable,
            args: Iterable[str] = (), env: Mapping[str, str] | None = None,
            timeout: float | None = None) -> Path:
        """Verify all declared files before spawning a declared Python entry point.

        Native launch/imports happen only after verification. The caller remains
        responsible for any task-specific execution authorization and guards.
        """
        _relative(entrypoint)
        if entrypoint not in self.files or not entrypoint.endswith(".py"):
            raise ValueError("entrypoint must be a declared Python source file")
        return ProcessCommand(
            "source-run", (str(python), str(self.root / entrypoint), *args), self.root,
            env={} if env is None else env, timeout=timeout, sources=self,
        ).execute(log_dir).receipt_path

    def archive(self, output: str | Path) -> str:
        """Write a deterministic source-only tar.gz and embedded v1 manifest.

        Returns the archive SHA-256. Existing output is never replaced. No
        extraction or source execution is performed; dependencies are not bundled.
        """
        self._require_verified()
        content = {}
        for name, expected in sorted(self.files.items()):
            if name == "SOURCE_MANIFEST.json":
                raise ValueError("SOURCE_MANIFEST.json is reserved for the embedded manifest")
            path = (self.root / name).resolve()
            path.relative_to(self.root)
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise SourceVerificationError("source changed while packaging: " + name)
            content[name] = raw
        content["SOURCE_MANIFEST.json"] = json.dumps(
            {"schema": "benchstudio_source_snapshot_v1", "files": dict(sorted(self.files.items()))},
            sort_keys=True, indent=2).encode("utf-8")
        with Path(output).open("xb") as destination:
            with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as archive:
                    for name, raw in sorted(content.items()):
                        info = tarfile.TarInfo(name)
                        info.size, info.mode, info.mtime = len(raw), 0o644, 0
                        archive.addfile(info, io.BytesIO(raw))
        return hashlib.sha256(Path(output).read_bytes()).hexdigest()


# Runs under the selected native interpreter (Python 3.8+); no BenchStudio import.
_IMPORT_PROBE = r'''
import importlib, json, sys, traceback
results = []
for name in sys.argv[2:]:
    try:
        module = importlib.import_module(name)
        results.append({"name": name, "ok": True,
                        "origin": getattr(module, "__file__", None),
                        "version": str(getattr(module, "__version__", "unknown"))})
    except BaseException:
        results.append({"name": name, "ok": False, "error": traceback.format_exc()})
        break
ok = all(item["ok"] for item in results)
with open(sys.argv[1], "x") as stream:
    json.dump({"ok": ok, "executable": sys.executable, "python": sys.version,
               "imports": results}, stream, indent=2)
sys.exit(0 if ok else 1)
'''


def check_imports(*modules: str, python: str = sys.executable,
                  log_dir: str | Path, timeout: float = 60) -> dict:
    """Explicit import-only diagnostic in a clean, isolated native subprocess.

    Imports execute installed modules' top-level code; this is not a sandbox or
    proof that a module has no side effects. No environment is constructed by
    BenchStudio and no task authorization or consumption registry is accessed.
    Python -I ignores PYTHONPATH/user-site and current-directory shadow modules.
    """
    if not modules or any(not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", name) for name in modules):
        raise ValueError("supply valid module names")
    logs = Path(log_dir).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    result_path = logs / "imports.json"
    if result_path.exists():
        raise FileExistsError(result_path)
    with tempfile.TemporaryDirectory(prefix="benchstudio-imports-") as clean:
        command = ProcessCommand("imports", (str(python), "-I", "-c", _IMPORT_PROBE,
                                             str(result_path), *modules), clean, timeout=timeout)
        # Propagate failure even if an imported module attempts sys.exit(0).
        command.execute(logs)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("ok") is not True:
        raise ProcessFailure("import diagnostic failed; see " + str(result_path))
    return result
