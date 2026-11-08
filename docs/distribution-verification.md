# Verify an installed research-preview distribution

Run from an authorized checkout with its declared setuptools build backend and
wheel tooling already installed:

```sh
python scripts/check_distribution.py --output /absolute/path/to/a/fresh/check-directory
```

To also verify discovery and inert preparation of the separately installed
Excalidraw integration:

```sh
python scripts/check_distribution.py \
  --output /absolute/path/to/a/fresh/check-directory \
  --excalidraw-root /absolute/path/to/excalidraw-curriculum
```

The checker builds wheel/sdist without build isolation, installers or network
resolution; builds a second wheel from the extracted sdist; creates two fresh
venvs; installs each wheel with --no-index --no-deps; executes the real arithmetic
example from an empty directory; saves and reopens results; checks the supported
root API and the single installed `benchstudio` command, including its `campaign` and `replay`
specialist subcommands. Optional Excalidraw checking builds/installs its wheel
and discovers its actual metadata entry point; check() reads existing fixture
tasks and never invokes the agent or constructs a gym. It does not qualify
Excalidraw's full optional dependency stack.

The committed [0.1.0rc2 verification record](release-verification-0.1.0rc2.json)
records Python version, artifact hashes, source hashes and outcomes. A local
`build.log` retains the full command output. Wheel timestamps can differ; bit-for-bit reproducible
builds across hosts are not claimed. The script publishes nothing and does not
run simulators, GPUs, learned models or confirmation experiments.

On 8 November 2026 the local candidate passed the package checks on Python
3.12.14. The wheel exposes one console script, `benchstudio`; campaign and replay
are subcommands. The installed Excalidraw integration was not supplied to this run, so
its factory discovery and inert preparation check were not executed here. The
offline source suite passed 89 tests; the final selected API/system/integration
suite passed 195. These selections overlap and are not the complete repository
suite. Python 3.10/3.11 runtime verification is pending. Known native
qualification gaps remain listed in research-preview.md. Public release still
needs the final rights/security review and owner authorization.
