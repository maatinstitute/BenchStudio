"""Build and check local distributions offline; never publish or run native stacks."""
import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import venv
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--excalidraw-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    log = (output / "build.log").open("w")
    def run(argv, cwd):
        subprocess.run(list(map(str, argv)), cwd=cwd, check=True, stdout=log,
                       stderr=subprocess.STDOUT)
    def build(method, source, destination):
        destination.mkdir()
        # Uses installed build tooling; no installer, dependency resolution or network.
        run([sys.executable, "-c", f"from setuptools.build_meta import {method}; "
             f"{method}({str(destination)!r})"], source)
    build("build_sdist", root, output / "sdist")
    build("build_wheel", root, output / "wheel")
    sdist = next((output / "sdist").glob("*.tar.gz"))
    extracted = output / "extracted"
    extracted.mkdir()
    with tarfile.open(sdist) as archive:
        # Only extract regular files/directories from our own freshly built artifact.
        members = archive.getmembers()
        for member in members:
            target = (extracted / member.name).resolve()
            if not target.is_relative_to(extracted) or not (member.isfile() or member.isdir()):
                raise ValueError("unsafe distribution member")
        for member in members:
            target = extracted / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source_file = archive.extractfile(member)
            if source_file is None:
                raise ValueError("distribution member has no file data")
            with source_file, target.open("wb") as destination:
                shutil.copyfileobj(source_file, destination)
    source = next(extracted.iterdir())
    for required in ("LICENSE", "CONTRIBUTING.md", "docs/research-preview.md",
                     "docs/distribution-verification.md", "examples/research_preview.py"):
        if not (source / required).is_file():
            raise ValueError("sdist missing " + required)
    build("build_wheel", source, output / "rebuilt-wheel")
    integration_wheel = None
    if args.excalidraw_root is not None:
        build("build_wheel", args.excalidraw_root.resolve(), output / "excalidraw-wheel")
        integration_wheel = next((output / "excalidraw-wheel").glob("*.whl"))
    verified = []
    for label in ("wheel", "rebuilt-wheel"):
        wheel = next((output / label).glob("*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            metadata = BytesParser().parsebytes(archive.read(next(n for n in names if n.endswith(".dist-info/METADATA"))))
            entry_points = archive.read(next(n for n in names if n.endswith(".dist-info/entry_points.txt"))).decode()
            script_names = [line.split("=", 1)[0].strip() for line in entry_points.splitlines()
                            if "=" in line]
            assert metadata["Version"] == "0.1.0rc2"
            assert metadata.get_all("License-File") and any(n.endswith("/LICENSE") for n in names)
            assert script_names == ["benchstudio"]
            assert "benchstudio/results.py" in names
            assert "benchstudio/compat.py" not in names
            assert "benchstudio/vllm_backend.py" not in names
            assert not any(n.startswith(("tests/", "experiments/")) for n in names)
        environment = output / (label + "-env")
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        run([python, "-m", "pip", "install", "--no-index", "--no-deps", wheel], output)
        empty = output / (label + "-empty")
        empty.mkdir()
        # The example is copied out of the checkout; import must resolve to wheel.
        smoke = empty / "smoke.py"
        smoke.write_text((root / "examples/research_preview.py").read_text())
        run([python, smoke, empty / "run"], empty)
        run([python, "-m", "benchstudio", "--help"], empty)
        run([python, "-m", "benchstudio", "campaign", "--help"], empty)
        run([python, "-m", "benchstudio", "replay", "--help"], empty)
        run([python, "-c", "import benchstudio as bs; "
             "assert len(bs.__all__)==15; "
             "assert all(hasattr(bs,n) for n in bs.__all__); "
             "assert 'site-packages' in bs.__file__; "
             "import benchstudio.integrations as integrations; "
             "assert bs.__version__=='0.1.0rc2'; "
             "assert 'ProcessCommand' not in bs.__all__; assert not hasattr(bs,'ProcessCommand'); "
             "assert not hasattr(bs,'__getattr__'); "
             "assert not hasattr(integrations,'__getattr__'); "
             "assert not hasattr(integrations,'FixedReference'); "
             "assert not hasattr(bs.System,'from_pretrained'); "
             "assert not hasattr(bs.Benchmark,'from_pretrained'); "
             "assert 'benchstudio.vllm_backend' not in __import__('sys').modules"], empty)
        if integration_wheel is not None:
            run([python, "-m", "pip", "install", "--no-index", "--no-deps", integration_wheel], output)
            plugin_check = empty / "plugin_check.py"
            plugin_check.write_text("""from pathlib import Path
from types import SimpleNamespace
import sys
import benchstudio as bs

def refuse(*args, **kwargs):
    raise AssertionError('check must not invoke agent')

benchmark = bs.Benchmark.load('excalidraw', revision='installation-fixture',
    root=Path(sys.argv[1]), task_root=Path('tasks/excalidraw'), seeds=(4, 9),
    agent_revision='installation-fixture', isolation=bs.EpisodeIsolation(stateless=True))
evaluation = bs.pipeline(system=SimpleNamespace(name='never-called', act=refuse), benchmark=benchmark)
assert evaluation.check().configuration_valid
assert evaluation.check().cases == 4
assert evaluation.check().native_verified is False
assert not evaluation.capabilities['async']
print('Installed Excalidraw factory discovery and inert check passed; native execution unverified')
""")
            run([python, plugin_check, args.excalidraw_root.resolve()], empty)
        verified.append({"origin": label, "artifact": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                         "installed_example": "passed", "installed_cli": "passed",
                         "installed_campaign_help": "passed", "installed_replay_help": "passed",
                         "installed_excalidraw_check": integration_wheel is not None})
    log.close()
    bound_files = list((root / "src/benchstudio").rglob("*.py"))
    bound_files += [root / p for p in ("pyproject.toml", "LICENSE", "README.md",
        "CONTRIBUTING.md", "MANIFEST.in", "CHANGELOG.md", "scripts/check_distribution.py",
        "examples/research_preview.py", "docs/research-preview.md",
        "docs/distribution-verification.md", "docs/public-release-readiness.md",
        "docs/specialist-workflows.md", "docs/source-attribution.md")]
    source_hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(bound_files)}
    report = {"python": sys.version, "artifacts": verified, "source_sha256": source_hashes,
              "sdist_sha256": hashlib.sha256(sdist.read_bytes()).hexdigest(),
              "native_model_simulator_execution": False, "published": False}
    (output / "verification.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
